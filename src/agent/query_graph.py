from __future__ import annotations

import re
import uuid
from typing import Any

from langgraph.graph import END, StateGraph

from src.config.settings import get_settings
from src.generation.answerer import Answerer
from src.models.agent import AgentState, ReflectionResult, VerificationResult
from src.retrieval.query_signals import (
    extract_clause_ids_from_query,
    wants_appearance_clauses,
    wants_table_evidence,
)
from src.retrieval.retriever import HybridRetriever


REFUSE_TEMPLATE = "根据已检索的文档内容，无法可靠回答该问题。建议核对问题是否与《键 技术条件》标准相关。"

_OUT_OF_SCOPE_MARKERS = ("蓝牙", "加密协议", "手机", "Wi-Fi", "wifi", "配对")


def _is_out_of_scope_question(question: str) -> bool:
    return any(m in question for m in _OUT_OF_SCOPE_MARKERS)


def _target_clause_in_evidence(state: AgentState) -> bool:
    targets = extract_clause_ids_from_query(state.get("question", ""))
    if not targets:
        return False
    for e in state.get("evidence") or []:
        if (e.get("clause_id") or "") in targets:
            return True
    return False


def _has_answerable_evidence(state: AgentState) -> bool:
    """有目标条款、外观条款或表块时，避免 reflect 误拒。"""
    if _target_clause_in_evidence(state):
        return True
    q = state.get("question", "")
    for e in state.get("evidence") or []:
        cid = e.get("clause_id") or ""
        if wants_appearance_clauses(q) and cid in ("3.2", "3.3"):
            return True
        if wants_table_evidence(q) and e.get("chunk_type") == "table":
            return True
    return False


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
        if _is_out_of_scope_question(state["question"]):
            return {
                **state,
                "evidence": [],
                "hard_refused": True,
                "verification": {
                    "has_evidence": False,
                    "hallucination_risk": "low",
                    "should_refuse": True,
                    "unsupported_claims": [],
                },
            }
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
        if _has_answerable_evidence(state):
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
        ver = dict(state.get("verification") or {})
        ver["should_refuse"] = True
        if state.get("hard_refused"):
            ver["has_evidence"] = False
            ver["hallucination_risk"] = "low"
        return {
            **state,
            "final_answer": REFUSE_TEMPLATE,
            "citations": [],
            "verification": ver,
        }

    def route_after_retrieve(state: AgentState) -> str:
        if state.get("hard_refused"):
            return "refuse"
        return "generate"

    def route_after_reflect(state: AgentState) -> str:
        last = state.get("_last_reflection", {})
        action = last.get("action", "accept")
        risk = last.get("hallucination_risk", "low")
        has_ev = len(state.get("evidence") or []) > 0
        if risk == "high":
            if _has_answerable_evidence(state) and state.get(
                "reflection_count", 0
            ) < settings.max_reflection:
                return "revise"
            return "refuse"
        if last.get("should_refuse"):
            if _has_answerable_evidence(state):
                if state.get("reflection_count", 0) < settings.max_reflection:
                    return "revise"
                return "respond"
            if has_ev and state.get("reflection_count", 0) < settings.max_reflection:
                return "revise"
            return "refuse"
        if action == "re_retrieve":
            if state.get("re_retrieve_count", 0) < settings.max_re_retrieve:
                return "rewrite_query"
            return "refuse"
        if action == "revise":
            if state.get("reflection_count", 0) < settings.max_reflection:
                return "revise"
            if last.get("unsupported_claims") and not _has_answerable_evidence(state):
                return "refuse"
            return "respond"
        if action == "refuse":
            if _has_answerable_evidence(state):
                return "respond"
            return "refuse"
        if last.get("unsupported_claims") and not _has_answerable_evidence(state):
            return "refuse"
        return "respond"

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
        route_after_reflect,
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
    return app.invoke(init)
