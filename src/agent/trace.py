"""LangGraph execution trace helpers for UI / debugging."""
from __future__ import annotations

from typing import Any

from src.models.agent import AgentState


def get_graph_mermaid() -> str:
    from src.agent.query_graph import build_query_graph

    return build_query_graph().get_graph().draw_mermaid()


def _summarize_step(node: str, delta: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"node": node}
    if node == "retrieve":
        summary["evidence_count"] = len(delta.get("evidence") or [])
        summary["hard_refused"] = bool(delta.get("hard_refused"))
        ver = delta.get("verification") or {}
        summary["rerank_before_top1"] = ver.get("rerank_before_top1")
        summary["rerank_after_top1"] = ver.get("rerank_after_top1")
        summary["reranker_degraded"] = ver.get("reranker_degraded")
    elif node == "generate":
        draft = delta.get("draft_answer") or ""
        summary["draft_preview"] = draft[:200] + ("…" if len(draft) > 200 else "")
    elif node == "reflect":
        last = delta.get("_last_reflection") or {}
        summary["action"] = last.get("action")
        summary["hallucination_risk"] = last.get("hallucination_risk")
        summary["should_refuse"] = last.get("should_refuse")
        summary["unsupported_claims"] = last.get("unsupported_claims", [])
        summary["critique_preview"] = (last.get("critique") or "")[:160]
        summary["reflection_round"] = delta.get("reflection_count")
    elif node == "revise":
        draft = delta.get("draft_answer") or ""
        summary["revised_preview"] = draft[:200] + ("…" if len(draft) > 200 else "")
    elif node == "rewrite_query":
        summary["rewritten_query"] = delta.get("rewritten_query")
        summary["retrieval_round"] = delta.get("retrieval_round")
    elif node == "respond":
        summary["citation_count"] = len(delta.get("citations") or [])
        ans = delta.get("final_answer") or ""
        summary["final_preview"] = ans[:200] + ("…" if len(ans) > 200 else "")
    elif node == "refuse":
        summary["final_preview"] = (delta.get("final_answer") or "")[:200]
        summary["should_refuse"] = True
    return summary


def run_query_with_trace(
    question: str,
    question_id: str | None = None,
    session_id: str | None = None,
) -> tuple[AgentState, list[dict[str, Any]]]:
    import uuid

    from src.agent.query_graph import build_query_graph

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
    merged: dict[str, Any] = dict(init)
    trace: list[dict[str, Any]] = []
    step_idx = 0
    from src.observability.langfuse_telemetry import query_trace_context, span_context

    with query_trace_context(
        session_id=sid,
        question=question,
        question_id=question_id,
    ):
        for update in app.stream(init, stream_mode="updates"):
            for node_name, delta in update.items():
                step_idx += 1
                merged.update(delta)
                summary = _summarize_step(node_name, delta)
                with span_context(
                    f"graph.{node_name}",
                    metadata=summary,
                    input={"question": question, "node": node_name},
                    output=summary,
                ):
                    pass
                trace.append(
                    {
                        "step": step_idx,
                        "node": node_name,
                        "summary": summary,
                        "state_delta_keys": sorted(delta.keys()),
                    }
                )
    return merged, trace  # type: ignore[return-value]
