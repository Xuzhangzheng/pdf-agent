from __future__ import annotations

import re
import uuid
from typing import Any

from langgraph.graph import END, StateGraph

from src.agent.refusal import (
    REFUSE_TEMPLATE,
    apply_refuse_verification,
    has_answerable_evidence,
    route_after_reflect,
)
from src.config.settings import get_settings
from src.generation.answerer import Answerer
from src.models.agent import AgentState, VerificationResult
from src.retrieval.query_signals import extract_clause_ids_from_query
from src.retrieval.retriever import HybridRetriever


def _enrich_citations_from_evidence(
    cites: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if any(c.get("table_id") for c in cites):
        return cites
    for e in evidence:
        if e.get("chunk_type") == "table" and e.get("table_id"):
            cites.append(
                {
                    "page": e.get("page"),
                    "snippet": (e.get("text") or "")[:80],
                    "clause_id": None,
                    "table_id": e.get("table_id"),
                }
            )
            break
    return cites


def _extract_citations(answer: str) -> list[dict[str, Any]]:
    cites: list[dict[str, Any]] = []
    seen_pages: set[int] = set()

    def add_cite(page: int, extra: str, span: tuple[int, int]) -> None:
        if page in seen_pages:
            return
        seen_pages.add(page)
        clause_id = None
        table_id = None
        cm = re.search(r"条款([\d.]+)", extra)
        if cm:
            clause_id = cm.group(1)
        tm = re.search(r"表\s*(\d+)", extra)
        if tm:
            table_id = f"表{tm.group(1)}"
        cites.append(
            {
                "page": page,
                "snippet": answer[max(0, span[0] - 40) : span[1] + 40],
                "clause_id": clause_id,
                "table_id": table_id,
            }
        )

    for m in re.finditer(r"\[p\.(\d+)([^\]]*)\]", answer):
        add_cite(int(m.group(1)), m.group(2).strip(), (m.start(), m.end()))

    if not cites:
        for m in re.finditer(r"p\.(\d+)", answer):
            start = max(0, m.start() - 20)
            end = min(len(answer), m.end() + 30)
            extra = answer[start:end]
            add_cite(int(m.group(1)), extra, (m.start(), m.end()))

    return cites


def build_query_graph():
    settings = get_settings()
    retriever = HybridRetriever(settings)
    answerer = Answerer()

    def retrieve_node(state: AgentState) -> AgentState:
        q = state.get("rewritten_query") or state["question"]
        out = retriever.retrieve(
            q,
            question_id=state.get("question_id"),
            retrieval_round=state.get("retrieval_round", 0),
            session_id=state.get("session_id"),
        )
        ev = [e.model_dump() for e in out.evidence]
        ver = state.get("verification") or {}
        ver.update(
            {
                "reranker_degraded": out.reranker_degraded,
                "rerank_before_top1": out.rerank_before_top1,
                "rerank_after_top1": out.rerank_after_top1,
            }
        )
        return {
            **state,
            "evidence": ev,
            "hard_refused": out.hard_refuse,
            "reranker_degraded": out.reranker_degraded,
            "verification": ver,
        }

    def generate_node(state: AgentState) -> AgentState:
        from src.models.agent import Evidence

        evidence = [Evidence.model_validate(e) for e in state.get("evidence", [])]
        draft = answerer.generate_draft(
            state["question"],
            evidence,
            question_id=state.get("question_id"),
            session_id=state.get("session_id"),
            retrieval_round=state.get("retrieval_round", 0),
        )
        return {**state, "draft_answer": draft}

    def reflect_node(state: AgentState) -> AgentState:
        from src.models.agent import Evidence

        evidence = [Evidence.model_validate(e) for e in state.get("evidence", [])]
        reflection = answerer.reflect(
            state["question"],
            evidence,
            state.get("draft_answer", ""),
            question_id=state.get("question_id"),
            session_id=state.get("session_id"),
            retrieval_round=state.get("retrieval_round", 0),
        )
        notes = list(state.get("reflection_notes", []))
        notes.append(reflection.model_dump())
        ver = VerificationResult(
            has_evidence=reflection.has_evidence,
            hallucination_risk=reflection.hallucination_risk,
            should_refuse=reflection.should_refuse,
            unsupported_claims=reflection.unsupported_claims,
            reflection_rounds=state.get("reflection_count", 0) + 1,
            re_retrieve_count=state.get("re_retrieve_count", 0),
            retrieval_round=state.get("retrieval_round", 0),
            reranker_degraded=state.get("reranker_degraded", False),
        )
        return {
            **state,
            "reflection_notes": notes,
            "reflection_count": state.get("reflection_count", 0) + 1,
            "verification": ver.model_dump(),
            "_last_reflection": reflection.model_dump(),
        }

    def revise_node(state: AgentState) -> AgentState:
        from src.models.agent import Evidence

        evidence = [Evidence.model_validate(e) for e in state.get("evidence", [])]
        last = state.get("_last_reflection", {})
        critique = last.get("critique", "")
        draft = answerer.revise(
            state["question"],
            evidence,
            state.get("draft_answer", ""),
            critique,
            question_id=state.get("question_id"),
            session_id=state.get("session_id"),
            retrieval_round=state.get("retrieval_round", 0),
        )
        return {**state, "draft_answer": draft}

    def rewrite_query_node(state: AgentState) -> AgentState:
        last = state.get("_last_reflection", {})
        rq = answerer.rewrite_query(
            state["question"],
            last.get("critique", ""),
            question_id=state.get("question_id"),
            session_id=state.get("session_id"),
        )
        clause_ids = extract_clause_ids_from_query(state["question"])
        if clause_ids and clause_ids[0] not in rq:
            rq = f"{rq} 条款{clause_ids[0]}"
        return {
            **state,
            "rewritten_query": rq,
            "re_retrieve_count": state.get("re_retrieve_count", 0) + 1,
            "retrieval_round": state.get("retrieval_round", 0) + 1,
            "evidence": [],
        }

    def respond_node(state: AgentState) -> AgentState:
        answer = state.get("draft_answer", "")
        ver = dict(state.get("verification") or {})
        ver["should_refuse"] = False
        if has_answerable_evidence(state):
            ver["unsupported_claims"] = []
        cites = _extract_citations(answer)
        cites = _enrich_citations_from_evidence(
            cites, state.get("evidence") or []
        )
        if not cites and state.get("evidence"):
            for e in state.get("evidence") or []:
                if e.get("page"):
                    cites.append(
                        {
                            "page": e.get("page"),
                            "snippet": (e.get("text") or "")[:80],
                            "clause_id": e.get("clause_id"),
                            "table_id": e.get("table_id"),
                        }
                    )
                    if len(cites) >= 1:
                        break
        return {
            **state,
            "final_answer": answer,
            "citations": cites,
            "verification": ver,
        }

    def refuse_node(state: AgentState) -> AgentState:
        return {
            **state,
            "final_answer": REFUSE_TEMPLATE,
            "citations": [],
            "verification": apply_refuse_verification(state),
        }

    def route_after_retrieve(state: AgentState) -> str:
        if state.get("hard_refused"):
            return "refuse"
        return "generate"

    def route_after_reflect_node(state: AgentState) -> str:
        return route_after_reflect(state, settings=settings)

    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("revise", revise_node)
    graph.add_node("rewrite_query", rewrite_query_node)
    graph.add_node("respond", respond_node)
    graph.add_node("refuse", refuse_node)

    graph.set_entry_point("retrieve")
    graph.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"generate": "generate", "refuse": "refuse"},
    )
    graph.add_edge("generate", "reflect")
    graph.add_conditional_edges(
        "reflect",
        route_after_reflect_node,
        {
            "respond": "respond",
            "revise": "revise",
            "rewrite_query": "rewrite_query",
            "refuse": "refuse",
        },
    )
    graph.add_edge("revise", "reflect")
    graph.add_edge("rewrite_query", "retrieve")
    graph.add_edge("respond", END)
    graph.add_edge("refuse", END)

    return graph.compile()


def run_query(
    question: str,
    question_id: str | None = None,
    session_id: str | None = None,
) -> AgentState:
    from src.observability.langfuse_telemetry import query_trace_context

    app = build_query_graph()
    sid = session_id or str(uuid.uuid4())
    init: AgentState = {
        "question": question,
        "question_id": question_id,
        "session_id": sid,
        "reflection_count": 0,
        "re_retrieve_count": 0,
        "retrieval_round": 0,
        "reflection_notes": [],
        "evidence": [],
    }
    with query_trace_context(
        session_id=sid,
        question=question,
        question_id=question_id,
    ):
        return app.invoke(init)
