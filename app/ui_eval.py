"""评测报告：JSON + 中文解读（与入库质量闸门区分）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from src.config.settings import Settings, get_settings

_METRIC_SPECS: list[tuple[str, str, str, str]] = [
    (
        "refuse_accuracy",
        "拒答准确率",
        "100%",
        "期望拒答题应触发 should_refuse",
    ),
    (
        "false_refuse_rate",
        "误拒答率",
        "0%",
        "应答题不应被误拒",
    ),
    (
        "citation_compliance",
        "引用合规率",
        "100%",
        "答题须含足够引用且含页码",
    ),
    (
        "table_retrieval_hit",
        "表格检索命中",
        "100%",
        "表题相关问句 Top-K 须含 table 块",
    ),
    (
        "clause_retrieval_hit",
        "条款检索命中",
        f"≥阈值",
        "条款问句 Top-K 须命中条款块",
    ),
    (
        "reflection_fields_present",
        "反思字段完整",
        "100%",
        "含 has_evidence / hallucination_risk / should_refuse",
    ),
    (
        "unsupported_claims_empty",
        "无 unsupported 主张",
        "100%",
        "accept 题 unsupported_claims 应为空",
    ),
    (
        "llm_judge_pass_rate",
        "LLM Judge 通过率",
        "≥80%",
        "语义判分，重跑可能波动",
    ),
    (
        "fuzzy_recall_pass",
        "模糊问召回",
        "通过",
        "口语问法与清晰版检索 Jaccard",
    ),
    (
        "ocr_robust_pass",
        "OCR 鲁棒题",
        "通过",
        "含 typo 的问句仍应检索命中",
    ),
    (
        "regression_consistency",
        "回归一致性",
        "通过",
        "同组问法答案/拒答应一致",
    ),
]


def _check_metric(key: str, value: Any, settings: Settings) -> bool | None:
    if value is None:
        return None
    if key == "refuse_accuracy":
        return float(value) >= 1.0
    if key == "false_refuse_rate":
        return float(value) <= 0.0
    if key in ("citation_compliance", "reflection_fields_present", "unsupported_claims_empty"):
        return float(value) >= 1.0
    if key in ("table_retrieval_hit",):
        return bool(value) if isinstance(value, bool) else float(value) >= 1.0
    if key == "clause_retrieval_hit":
        return float(value) >= settings.clause_hit_threshold
    if key == "llm_judge_pass_rate":
        return float(value) >= 0.8
    if key in ("fuzzy_recall_pass", "ocr_robust_pass", "regression_consistency"):
        return bool(value)
    return None


def _threshold_label(key: str, settings: Settings) -> str:
    if key == "clause_retrieval_hit":
        return f"≥ {settings.clause_hit_threshold:.0%}"
    for k, _, thresh, _ in _METRIC_SPECS:
        if k == key:
            return thresh.replace("≥阈值", f"≥ {settings.clause_hit_threshold:.0%}")
    return "—"


def _failed_reasons(metrics: dict[str, Any], settings: Settings) -> list[str]:
    reasons: list[str] = []
    for key, _label, _thresh, hint in _METRIC_SPECS:
        if key not in metrics:
            continue
        ok = _check_metric(key, metrics[key], settings)
        if ok is False:
            reasons.append(f"**{_label}**（`{key}`={metrics[key]}）：{hint}")
    if not metrics.get("eval_overall_pass", True):
        if metrics.get("llm_judge_pass_rate", 1.0) < 0.8:
            reasons.append(
                "**LLM Judge 未达 80%** 常见于 Judge 非确定性，可重跑 "
                "`python scripts/evaluate.py`，不必先怀疑 ingest 闸门。"
            )
    return reasons


def render_eval_report(
    rep: dict[str, Any],
    *,
    settings: Settings | None = None,
    index_ready: bool = True,
    ingest_quality_passed: bool | None = None,
) -> None:
    settings = settings or get_settings()
    metrics = rep.get("metrics", {})
    overall = rep.get("eval_overall_pass", metrics.get("eval_overall_pass"))
    run_at = rep.get("run_at", "—")
    run_id = rep.get("run_id", "—")

    st.markdown(
        f'<div class="doubao-card"><h4>构建阶段评测（eval_overall_pass）</h4>'
        f'<p class="doubao-muted">这是 <b>离线构建阶段</b>：9 题题库 + '
        f'<code>scripts/evaluate.py</code> 的硬性指标，'
        f"<b>不是</b> 入库质量闸门，也<b>不是</b>「会话评测」Tab 的历史对话质检。</p>"
        f'<p><span class="{"doubao-pass" if overall else "doubao-fail"}">'
        f'{"✓ 评测通过" if overall else "✗ 评测未通过"}</span></p>'
        f"<p class=\"doubao-muted\">run_at: {run_at} · run_id: {run_id}</p></div>",
        unsafe_allow_html=True,
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("构建阶段 eval_overall_pass", "通过" if overall else "未通过")
    with col_b:
        if ingest_quality_passed is None:
            st.metric("入库质量闸门 quality.passed", "未知")
        else:
            st.metric(
                "入库质量闸门 quality.passed",
                "通过" if ingest_quality_passed else "未通过",
            )

    if not index_ready:
        st.warning(
            "索引未就绪：请先 ingest。此时评测失败可能因未建索引，而非 RAG 逻辑本身。"
        )
    elif ingest_quality_passed is False:
        st.warning(
            "入库质量闸门未通过：请先修复解析/ingest（见「解析预览」质量报告）。"
            "eval_overall_pass=false 可能与此有关，不等同于「答题能力不达标」。"
        )

    if not overall:
        reasons = _failed_reasons(metrics, settings)
        if reasons:
            st.markdown("#### 未通过原因解读")
            for r in reasons:
                st.markdown(f"- {r}")

    st.markdown("#### 指标明细")
    table_rows: list[dict[str, str]] = []
    for key, label, _thresh, hint in _METRIC_SPECS:
        if key not in metrics:
            continue
        val = metrics[key]
        ok = _check_metric(key, val, settings)
        status = "—"
        if ok is True:
            status = "达标"
        elif ok is False:
            status = "未达标"
        table_rows.append(
            {
                "指标": label,
                "键": key,
                "值": str(val),
                "阈值": _threshold_label(key, settings),
                "状态": status,
                "说明": hint,
            }
        )
    if table_rows:
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

    per_q = rep.get("per_question_results", [])
    if per_q:
        st.markdown("#### 逐题结果")
        st.dataframe(per_q, use_container_width=True, hide_index=True)
        failed = [
            r
            for r in per_q
            if not r.get("llm_judge_pass", True) and r.get("expected_behavior") == "answer"
        ]
        if failed:
            with st.expander(f"未通过 Judge 的题目（{len(failed)}）", expanded=False):
                for r in failed:
                    st.markdown(f"**{r.get('id', '')}**：{r.get('question', '')[:80]}…")

    with st.expander("原始 metrics JSON", expanded=False):
        st.json(metrics)
    with st.expander("cost_summary JSON", expanded=False):
        st.json(rep.get("cost_summary", {}))


def load_ingest_quality_passed(parsed_dir: Path) -> bool | None:
    doc_path = parsed_dir / "doc.json"
    if not doc_path.is_file():
        return None
    import json

    try:
        data = json.loads(doc_path.read_text(encoding="utf-8"))
        return bool(data.get("quality", {}).get("passed"))
    except (json.JSONDecodeError, OSError):
        return None
