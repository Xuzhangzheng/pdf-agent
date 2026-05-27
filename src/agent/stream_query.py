"""Streaming Q&A for chat API (SSE): retrieve → stream generate → reflect/revise."""
from __future__ import annotations

import json
import uuid
from typing import Any, Iterator

from src.agent.orchestrator import _ensure_index
from src.agent.query_graph import (
    REFUSE_TEMPLATE,
    _enrich_citations_from_evidence,
    _extract_citations,
    _has_answerable_evidence,
    _is_out_of_scope_question,
)
from src.config.settings import get_settings
from src.generation.answerer import Answerer
from src.models.agent import AgentState, Evidence
from src.observability.langfuse_telemetry import flush_langfuse, query_trace_context
from src.retrieval.retriever import HybridRetriever


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _state_from_evidence(
    question: str,
    evidence: list[Evidence],
    draft: str,
) -> AgentState:
    ev_dicts = [e.model_dump() for e in evidence]
    return {
        "question": question,
        "evidence": ev_dicts,
        "draft_answer": draft,
        "reflection_count": 0,
        "re_retrieve_count": 0,
        "retrieval_round": 0,
    }


def _route_after_reflect(state: AgentState, reflection: Any) -> str:
    settings = get_settings()
    action = reflection.action
    risk = reflection.hallucination_risk
    has_ev = len(state.get("evidence") or []) > 0
    if risk == "high":
        if _has_answerable_evidence(state) and state.get("reflection_count", 0) < settings.max_reflection:
            return "revise"
        return "refuse"
    if reflection.should_refuse:
        if _has_answerable_evidence(state):
            if state.get("reflection_count", 0) < settings.max_reflection:
                return "revise"
            return "respond"
        if has_ev and state.get("reflection_count", 0) < settings.max_reflection:
            return "revise"
        return "refuse"
    if action == "revise":
        if state.get("reflection_count", 0) < settings.max_reflection:
            return "revise"
        if reflection.unsupported_claims and not _has_answerable_evidence(state):
            return "refuse"
        return "respond"
    if action == "refuse":
        if _has_answerable_evidence(state):
            return "respond"
        return "refuse"
    if reflection.unsupported_claims and not _has_answerable_evidence(state):
        return "refuse"
    return "respond"


def stream_ask(
    question: str,
    *,
    chat_session_id: str,
    history: list[dict] | None = None,
) -> Iterator[str]:
    """Yield SSE frames (strings)."""
    _ensure_index()
    settings = get_settings()
    trace_id = str(uuid.uuid4())
    answerer = Answerer()
    retriever = HybridRetriever(settings)

    try:
        with query_trace_context(
            session_id=trace_id,
            question=question,
            question_id=chat_session_id,
        ):
            yield _sse("status", {"stage": "start", "trace_id": trace_id})

            if _is_out_of_scope_question(question):
                yield _sse("status", {"stage": "refuse"})
                yield _sse(
                    "done",
                    {
                        "answer": REFUSE_TEMPLATE,
                        "citations": [],
                        "verification": {
                            "should_refuse": True,
                            "has_evidence": False,
                            "hallucination_risk": "low",
                        },
                        "trace_id": trace_id,
                        "revised": False,
                    },
                )
                return

            yield _sse("status", {"stage": "retrieve"})
            out = retriever.retrieve(
                question,
                question_id=chat_session_id,
                session_id=trace_id,
            )
            if out.hard_refuse or not out.evidence:
                yield _sse("status", {"stage": "refuse"})
                yield _sse(
                    "done",
                    {
                        "answer": REFUSE_TEMPLATE,
                        "citations": [],
                        "verification": {
                            "should_refuse": True,
                            "has_evidence": False,
                            "hallucination_risk": "low",
                        },
                        "trace_id": trace_id,
                        "revised": False,
                    },
                )
                return

            yield _sse("status", {"stage": "generate"})
            draft = ""
            for chunk in answerer.generate_draft_stream(
                question,
                out.evidence,
                question_id=chat_session_id,
                session_id=trace_id,
                history=history,
            ):
                draft += chunk
                yield _sse("token", {"text": chunk})

            state = _state_from_evidence(question, out.evidence, draft)
            answer = draft
            revised = False
            reflection_rounds = 0

            while reflection_rounds < settings.max_reflection:
                yield _sse("status", {"stage": "reflect"})
                reflection = answerer.reflect(
                    question,
                    out.evidence,
                    answer,
                    question_id=chat_session_id,
                    session_id=trace_id,
                )
                reflection_rounds += 1
                state["reflection_count"] = reflection_rounds
                route = _route_after_reflect(state, reflection)

                if route == "revise":
                    yield _sse("status", {"stage": "revise"})
                    answer = answerer.revise(
                        question,
                        out.evidence,
                        answer,
                        reflection.critique,
                        question_id=chat_session_id,
                        session_id=trace_id,
                    )
                    revised = True
                    state["draft_answer"] = answer
                    continue
                if route == "refuse":
                    answer = REFUSE_TEMPLATE
                    break
                break

            ev_dicts = [e.model_dump() for e in out.evidence]
            cites = _extract_citations(answer)
            cites = _enrich_citations_from_evidence(cites, ev_dicts)
            if not cites and ev_dicts and answer != REFUSE_TEMPLATE:
                for e in ev_dicts:
                    if e.get("page"):
                        cites.append(
                            {
                                "page": e.get("page"),
                                "snippet": (e.get("text") or "")[:80],
                                "clause_id": e.get("clause_id"),
                                "table_id": e.get("table_id"),
                            }
                        )
                        break

            verification = {
                "has_evidence": bool(out.evidence),
                "hallucination_risk": "low",
                "should_refuse": answer == REFUSE_TEMPLATE,
                "reflection_rounds": reflection_rounds,
            }

            yield _sse(
                "done",
                {
                    "answer": answer,
                    "citations": cites,
                    "verification": verification,
                    "trace_id": trace_id,
                    "revised": revised,
                    "streamed_draft": draft,
                },
            )
    except Exception as e:
        yield _sse("error", {"message": str(e)})
    finally:
        flush_langfuse()
