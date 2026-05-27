"""拒答：统一模板、reflect 路由与评测判定（无关键词捷径）。"""
from __future__ import annotations

import re
from typing import Any

from src.config.settings import Settings, get_settings
from src.models.agent import AgentState, ReflectionResult
from src.retrieval.query_signals import (
    TECH_REQUIREMENTS_CLAUSE_IDS,
    extract_clause_ids_from_query,
    wants_appearance_clauses,
    wants_table_evidence,
    wants_technical_requirements_overview,
)

REFUSE_TEMPLATE = (
    "根据已检索的文档内容，无法可靠回答该问题。建议核对问题是否与《键 技术条件》标准相关。"
)

_REFUSE_ANSWER_MARKERS = ("无法可靠回答", "无法从本文档回答")

# generate 草稿诚实声明「证据未涉及所问」时的常见表述（非关键词拒答）
_DRAFT_SEMANTIC_REFUSAL_HINTS = (
    "未涉及",
    "无法为你解答",
    "无法解答该问题",
    "无法可靠回答",
    "无法从本文档",
    "无法回答该问题",
    "与键标准无关",
    # "与《键",
    "不能回答",
)


def _target_clause_in_evidence(state: AgentState) -> bool:
    targets = extract_clause_ids_from_query(state.get("question", ""))
    if not targets:
        return False
    for e in state.get("evidence") or []:
        if (e.get("clause_id") or "") in targets:
            return True
    return False


def has_answerable_evidence(state: AgentState) -> bool:
    """问句目标条款、外观 3.2/3.3 或表块已在 evidence 中，可尝试作答而非拒答。"""
    if _target_clause_in_evidence(state):
        return True
    q = state.get("question", "")
    for e in state.get("evidence") or []:
        cid = e.get("clause_id") or ""
        if wants_appearance_clauses(q) and cid in ("3.2", "3.3"):
            return True
        if wants_table_evidence(q) and e.get("chunk_type") == "table":
            return True
        if wants_technical_requirements_overview(q):
            cid = e.get("clause_id") or ""
            if cid in TECH_REQUIREMENTS_CLAUSE_IDS:
                return True
            if "技术要求、验收检查" in (e.get("text") or ""):
                return True
    return False


def draft_indicates_semantic_refusal(state: AgentState) -> bool:
    """检索块存在但与问题无关时，generate 常已声明无法解答。"""
    if has_answerable_evidence(state):
        return False
    draft = state.get("draft_answer") or ""
    return any(h in draft for h in _DRAFT_SEMANTIC_REFUSAL_HINTS)


def _reflection_fields(
    reflection: ReflectionResult | dict[str, Any],
) -> tuple[bool, str, str, list[Any]]:
    if isinstance(reflection, dict):
        return (
            bool(reflection.get("should_refuse")),
            str(reflection.get("action", "accept")),
            str(reflection.get("hallucination_risk", "low")),
            list(reflection.get("unsupported_claims") or []),
        )
    return (
        reflection.should_refuse,
        reflection.action,
        reflection.hallucination_risk,
        list(reflection.unsupported_claims or []),
    )


def route_after_reflect(
    state: AgentState,
    reflection: ReflectionResult | dict[str, Any] | None = None,
    *,
    settings: Settings | None = None,
) -> str:
    """reflect 之后下一节点：respond / revise / rewrite_query / refuse。"""
    settings = settings or get_settings()
    last = reflection if reflection is not None else state.get("_last_reflection", {})
    should_refuse, action, risk, unsupported = _reflection_fields(last)

    if risk == "high":
        if has_answerable_evidence(state) and state.get(
            "reflection_count", 0
        ) < settings.max_reflection:
            return "revise"
        return "refuse"

    if should_refuse:
        if not has_answerable_evidence(state):
            return "refuse"
        if action == "refuse":
            return "refuse"
        if state.get("reflection_count", 0) < settings.max_reflection:
            return "revise"
        return "respond"

    if draft_indicates_semantic_refusal(state):
        return "refuse"

    if action == "re_retrieve":
        if state.get("re_retrieve_count", 0) < settings.max_re_retrieve:
            return "rewrite_query"
        return "refuse"

    if action == "revise":
        if state.get("reflection_count", 0) < settings.max_reflection:
            return "revise"
        if unsupported and not has_answerable_evidence(state):
            return "refuse"
        return "respond"

    if action == "refuse":
        if has_answerable_evidence(state):
            return "respond"
        return "refuse"

    if unsupported and not has_answerable_evidence(state):
        return "refuse"

    return "respond"


def apply_refuse_verification(state: AgentState) -> dict[str, Any]:
    ver = dict(state.get("verification") or {})
    ver["should_refuse"] = True
    ver["has_evidence"] = has_answerable_evidence(state)
    if state.get("hard_refused"):
        ver["has_evidence"] = False
        ver["hallucination_risk"] = "low"
    return ver


def is_refused_state(state: dict[str, Any]) -> bool:
    ver = state.get("verification") or {}
    if ver.get("should_refuse"):
        return True
    ans = state.get("final_answer") or ""
    if any(m in ans for m in _REFUSE_ANSWER_MARKERS):
        return True
    if REFUSE_TEMPLATE in ans:
        return True
    if "无法从本文档回答" in ans and not re.search(r"\[p\.\d+", ans):
        return True
    return False
