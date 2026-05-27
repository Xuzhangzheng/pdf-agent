from src.config.settings import get_settings

from app.ui_eval import _check_metric, _failed_reasons, _threshold_label


def test_check_refuse_accuracy():
    s = get_settings()
    assert _check_metric("refuse_accuracy", 1.0, s) is True
    assert _check_metric("refuse_accuracy", 0.5, s) is False


def test_check_llm_judge_threshold():
    s = get_settings()
    assert _check_metric("llm_judge_pass_rate", 0.85, s) is True
    assert _check_metric("llm_judge_pass_rate", 0.5, s) is False


def test_failed_reasons_includes_judge_hint():
    s = get_settings()
    metrics = {
        "refuse_accuracy": 1.0,
        "false_refuse_rate": 0.0,
        "citation_compliance": 1.0,
        "llm_judge_pass_rate": 0.5,
        "eval_overall_pass": False,
    }
    reasons = _failed_reasons(metrics, s)
    text = " ".join(reasons)
    assert "LLM Judge" in text or "llm_judge" in text.lower()


def test_threshold_label_clause():
    s = get_settings()
    label = _threshold_label("clause_retrieval_hit", s)
    assert str(s.clause_hit_threshold)[:3] in label or "80" in label
