"""拒答路由与判定（参考 tests/rejectAnswerExample.txt 中的流程调试状态）。"""
from __future__ import annotations

from src.agent.refusal import (
    REFUSE_TEMPLATE,
    apply_refuse_verification,
    draft_indicates_semantic_refusal,
    has_answerable_evidence,
    is_refused_state,
    route_after_reflect,
)
from src.config.settings import get_settings


def _example_irrelevant_state() -> dict:
    """钢筋混凝土抗震等级：5 条键标准证据，reflect#1 should_refuse=true。"""
    return {
        "question": "钢筋混凝土抗震等级",
        "reflection_count": 1,
        "evidence": [{"chunk_id": "c1", "text": "键的抗拉强度", "page": 1}] * 5,
        "_last_reflection": {
            "should_refuse": True,
            "action": "accept",
            "hallucination_risk": "low",
            "unsupported_claims": [],
        },
    }


def test_route_after_reflect_irrelevant_should_refuse_goes_refuse_not_revise():
    """修复前：has_ev>0 会误路由到 revise。"""
    state = _example_irrelevant_state()
    assert has_answerable_evidence(state) is False
    assert route_after_reflect(state, settings=get_settings()) == "refuse"


def test_route_after_reflect_action_refuse():
    state = {
        "question": "蓝牙加密",
        "reflection_count": 1,
        "evidence": [{"page": 1, "text": "键"}],
        "_last_reflection": {
            "should_refuse": True,
            "action": "refuse",
            "hallucination_risk": "low",
        },
    }
    assert route_after_reflect(state) == "refuse"


def test_apply_refuse_verification_has_evidence_false_when_not_answerable():
    state = _example_irrelevant_state()
    ver = apply_refuse_verification(state)
    assert ver["should_refuse"] is True
    assert ver["has_evidence"] is False


def test_is_refused_state_template_and_flag():
    assert is_refused_state(
        {
            "final_answer": REFUSE_TEMPLATE,
            "verification": {"should_refuse": True, "has_evidence": False},
        }
    )
    assert not is_refused_state(
        {
            "final_answer": "本标准适用于除花键外的各种键 [p.1]。",
            "verification": {"should_refuse": False},
        }
    )


def test_draft_semantic_refusal_routes_to_refuse():
    state = {
        "question": "本标准对手机蓝牙配对与加密协议有何要求？",
        "reflection_count": 1,
        "evidence": [{"page": 1, "text": "键的技术要求"}],
        "draft_answer": "证据均为键标准条文，未涉及手机蓝牙配对与加密协议。",
        "_last_reflection": {
            "should_refuse": False,
            "action": "accept",
            "hallucination_risk": "low",
        },
    }
    assert draft_indicates_semantic_refusal(state)
    assert route_after_reflect(state) == "refuse"


def test_no_keyword_shortcut_module():
    import src.agent.query_graph as qg

    assert not hasattr(qg, "_is_out_of_scope_question")
    assert not hasattr(qg, "_OUT_OF_SCOPE_MARKERS")
