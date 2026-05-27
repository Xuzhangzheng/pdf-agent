"""对 MongoDB 历史会话消息做离线质量评测（不重新跑 RAG）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.agent.refusal import is_refused_state
from src.config.settings import Settings, get_settings
from src.evaluation.llm_judge import LlmJudge

_SESSION_JUDGE_RUBRIC = (
    "仅根据「引用片段」判断助手回答是否被其支撑，无证据外臆造；"
    "若回答为拒答说明则判 pass。"
)


def _looks_refused(answer: str, verification: dict[str, Any]) -> bool:
    return is_refused_state(
        {"final_answer": answer, "verification": verification}
    )


def _citations_ok(citations: list[dict[str, Any]]) -> bool:
    if len(citations) < 1:
        return False
    return all(c.get("page") for c in citations)


def _reflection_ok(verification: dict[str, Any]) -> bool:
    return all(
        k in verification for k in ("has_evidence", "hallucination_risk", "should_refuse")
    )


def _citations_to_evidence_text(citations: list[dict[str, Any]], max_chars: int = 2000) -> str:
    parts: list[str] = []
    for i, c in enumerate(citations[:8], start=1):
        page = c.get("page", "?")
        text = (c.get("text") or c.get("snippet") or "")[:400]
        parts.append(f"[{i}] p.{page}: {text}")
    out = "\n".join(parts)
    return out[:max_chars]


def _pair_turns(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将消息流拆成 user -> assistant 轮次。"""
    turns: list[dict[str, Any]] = []
    pending_user: str | None = None
    turn_idx = 0
    for m in messages:
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        if role == "user":
            pending_user = content
            continue
        if role == "assistant" and pending_user is not None:
            turn_idx += 1
            turns.append(
                {
                    "turn_index": turn_idx,
                    "question": pending_user,
                    "answer": content,
                    "citations": m.get("citations") or [],
                    "verification": m.get("verification") or {},
                    "trace_id": m.get("trace_id"),
                }
            )
            pending_user = None
    return turns


def evaluate_session(
    session_id: str,
    messages: list[dict[str, Any]],
    *,
    session_title: str = "",
    settings: Settings | None = None,
    run_llm_judge: bool | None = None,
) -> dict[str, Any]:
    """基于已落库消息生成会话评测报告。"""
    settings = settings or get_settings()
    judge_enabled = (
        run_llm_judge
        if run_llm_judge is not None
        else settings.eval_llm_judge_enabled
    )
    turns = _pair_turns(messages)
    per_turn: list[dict[str, Any]] = []

    answer_turns = 0
    refuse_turns = 0
    citation_ok = 0
    reflection_ok = 0
    unsupported_ok = 0
    judge_total = 0
    judge_pass = 0

    judge = LlmJudge() if judge_enabled and settings.ark_api_key else None

    for t in turns:
        answer = t["answer"]
        ver = t["verification"]
        cites = t["citations"]
        refused = _looks_refused(answer, ver)

        row: dict[str, Any] = {
            "turn_index": t["turn_index"],
            "question_preview": t["question"][:120],
            "answer_preview": answer[:200],
            "refused": refused,
            "citation_count": len(cites),
            "trace_id": t.get("trace_id"),
        }

        if refused:
            refuse_turns += 1
            row["turn_pass"] = True
            per_turn.append(row)
            continue

        answer_turns += 1
        c_ok = _citations_ok(cites)
        r_ok = _reflection_ok(ver)
        u_ok = not (ver.get("unsupported_claims") or [])
        row["citation_ok"] = c_ok
        row["reflection_ok"] = r_ok
        row["unsupported_ok"] = u_ok

        if c_ok:
            citation_ok += 1
        if r_ok:
            reflection_ok += 1
        if u_ok:
            unsupported_ok += 1

        j_pass: bool | None = None
        if judge is not None:
            judge_total += 1
            ev_text = _citations_to_evidence_text(cites)
            try:
                v = judge.judge(
                    t["question"],
                    answer,
                    ev_text or "（无引用文本，仅 metadata）",
                    _SESSION_JUDGE_RUBRIC,
                    question_id=f"session-{session_id}-t{t['turn_index']}",
                    session_id=t.get("trace_id") or session_id,
                )
                j_pass = v.pass_
                row["llm_judge_pass"] = v.pass_
                row["llm_judge_reason"] = v.reason
                if v.pass_:
                    judge_pass += 1
            except Exception as e:
                row["llm_judge_error"] = str(e)
                j_pass = False

        row["turn_pass"] = c_ok and r_ok and u_ok and (
            j_pass is not False if judge is not None else True
        )
        per_turn.append(row)

    metrics: dict[str, Any] = {
        "turn_count": len(turns),
        "answer_turn_count": answer_turns,
        "refuse_turn_count": refuse_turns,
    }
    if answer_turns:
        metrics["citation_compliance"] = citation_ok / answer_turns
        metrics["reflection_fields_present"] = reflection_ok / answer_turns
        metrics["unsupported_claims_empty"] = unsupported_ok / answer_turns
    else:
        metrics["citation_compliance"] = 1.0
        metrics["reflection_fields_present"] = 1.0
        metrics["unsupported_claims_empty"] = 1.0

    if judge_total:
        metrics["llm_judge_pass_rate"] = judge_pass / judge_total
    else:
        metrics["llm_judge_pass_rate"] = None

    hard: list[bool] = []
    if answer_turns:
        hard.append(metrics["citation_compliance"] >= 1.0)
        hard.append(metrics["reflection_fields_present"] >= 1.0)
        hard.append(metrics["unsupported_claims_empty"] >= 1.0)
        if judge_total:
            hard.append(
                metrics["llm_judge_pass_rate"]
                >= settings.eval_llm_judge_pass_threshold
            )
    session_pass = bool(hard) and all(hard) if turns else False

    metrics["session_overall_pass"] = session_pass

    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "session_title": session_title,
        "message_count": len(messages),
        "metrics": metrics,
        "session_overall_pass": session_pass,
        "per_turn_results": per_turn,
    }
