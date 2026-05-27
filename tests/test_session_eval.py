from unittest.mock import MagicMock, patch

from src.evaluation.session_eval import _pair_turns, evaluate_session


def test_pair_turns_user_assistant():
    msgs = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1", "citations": [], "verification": {}},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2", "citations": [], "verification": {}},
    ]
    turns = _pair_turns(msgs)
    assert len(turns) == 2
    assert turns[0]["question"] == "Q1"
    assert turns[1]["answer"] == "A2"


def test_evaluate_session_refuse_turn_passes():
    msgs = [
        {"role": "user", "content": "蓝牙加密？"},
        {
            "role": "assistant",
            "content": "无法从本文档回答该问题。",
            "citations": [],
            "verification": {"should_refuse": True},
        },
    ]
    report = evaluate_session("sess-1", msgs, run_llm_judge=False)
    assert report["metrics"]["turn_count"] == 1
    assert report["metrics"]["refuse_turn_count"] == 1
    assert report["per_turn_results"][0]["turn_pass"] is True


def test_evaluate_session_answer_turn_citation_fail():
    msgs = [
        {"role": "user", "content": "范围是什么？"},
        {
            "role": "assistant",
            "content": "本标准规定了键的技术要求。",
            "citations": [],
            "verification": {
                "has_evidence": True,
                "hallucination_risk": "low",
                "should_refuse": False,
            },
        },
    ]
    report = evaluate_session("sess-2", msgs, run_llm_judge=False)
    assert report["session_overall_pass"] is False
    assert report["metrics"]["citation_compliance"] == 0.0


def test_evaluate_session_with_judge_mock():
    msgs = [
        {"role": "user", "content": "表1 内容？"},
        {
            "role": "assistant",
            "content": "见表1。",
            "citations": [{"page": 2, "text": "表1 数据"}],
            "verification": {
                "has_evidence": True,
                "hallucination_risk": "low",
                "should_refuse": False,
                "unsupported_claims": [],
            },
        },
    ]
    mock_verdict = MagicMock(pass_=True, reason="ok")
    with patch("src.evaluation.session_eval.LlmJudge") as cls:
        cls.return_value.judge.return_value = mock_verdict
        report = evaluate_session("sess-3", msgs, run_llm_judge=True)
    assert report["session_overall_pass"] is True
    assert report["metrics"]["llm_judge_pass_rate"] == 1.0
