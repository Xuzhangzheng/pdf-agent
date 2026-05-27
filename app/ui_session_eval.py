"""Streamlit：会话评测 Tab。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from src.config.settings import Settings
from src.evaluation.session_eval import evaluate_session


_SESSION_METRIC_SPECS: list[tuple[str, str, str]] = [
    ("citation_compliance", "引用合规率", "100%（非拒答轮）"),
    ("reflection_fields_present", "反思字段完整", "100%"),
    ("unsupported_claims_empty", "无 unsupported 主张", "100%"),
    ("llm_judge_pass_rate", "LLM Judge 通过率", "≥80%（若启用）"),
]


def _save_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def render_session_eval_tab(
    *,
    settings: Settings,
    api_ok: bool,
    api_get: Callable[[str], Any],
) -> None:
    st.subheader("会话评测")
    st.caption(
        "对 MongoDB 中**已结束的多轮会话**做离线质检：引用、自检字段、可选 LLM Judge。"
        "不重新调用 RAG；与「构建阶段评测报告」（9 题题库）相互独立。"
    )

    if not api_ok:
        st.error("需先启动 Chat API 与 Mongo：`bash scripts/run_api.sh`")
        return

    if "session_eval_reports" not in st.session_state:
        st.session_state["session_eval_reports"] = {}
    if "session_eval_target_id" not in st.session_state:
        st.session_state["session_eval_target_id"] = None

    try:
        sessions = api_get("/api/sessions")
    except Exception as e:
        st.error(f"无法加载会话列表：{e}")
        return

    left, right = st.columns([1, 2.2], gap="medium")

    with left:
        with st.container(border=True):
            st.markdown("##### 历史会话")
            if not sessions:
                st.caption("暂无会话，请先在「会话」Tab 中对话。")
            pick_id = st.session_state.get("session_eval_target_id")
            for s in sessions:
                sid = s.get("id", "")
                title = (s.get("title") or "新会话").strip()
                preview = sid[:8] + "…" if len(sid) > 8 else sid
                label = f"{title}\n{preview}"
                is_active = sid == pick_id
                if st.button(
                    label,
                    key=f"eval_pick_{sid}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state["session_eval_target_id"] = sid
                    st.rerun()

    with right:
        sid = st.session_state.get("session_eval_target_id")
        if not sid:
            st.markdown(
                '<div class="doubao-card"><p>请在左侧选择要评测的历史会话。</p></div>',
                unsafe_allow_html=True,
            )
            return

        sess_meta = next((x for x in sessions if x.get("id") == sid), {})
        title = sess_meta.get("title") or "新会话"

        try:
            messages = api_get(f"/api/sessions/{sid}/messages")
        except Exception as e:
            st.error(str(e))
            return

        st.markdown(f"**当前会话**：{title} · `{sid}`")
        st.caption(f"消息数 {len(messages)}（按时间序 user/assistant 配对为轮次）")

        with st.expander("会话消息预览", expanded=False):
            for m in messages:
                role = m.get("role", "user")
                with st.chat_message("user" if role == "user" else "assistant"):
                    st.markdown((m.get("content") or "")[:2000])

        run_judge = st.checkbox(
            "启用 LLM Judge（需 ARK_API_KEY）",
            value=settings.eval_llm_judge_enabled,
            key="session_eval_run_judge",
        )

        if st.button("生成会话评测报告", type="primary", key="session_eval_run"):
            with st.spinner("评测中…"):
                report = evaluate_session(
                    sid,
                    messages,
                    session_title=title,
                    settings=settings,
                    run_llm_judge=run_judge,
                )
                st.session_state["session_eval_reports"][sid] = report
                out_path = settings.resolve_path(
                    f"artifacts/session_eval/{sid}.json"
                )
                _save_report(out_path, report)
                st.success(f"已保存至 `{out_path}`")

        report = st.session_state.get("session_eval_reports", {}).get(sid)
        if report:
            _render_session_eval_report(report)


def _render_session_eval_report(report: dict[str, Any]) -> None:
    metrics = report.get("metrics", {})
    overall = report.get("session_overall_pass", metrics.get("session_overall_pass"))
    evaluated_at = report.get("evaluated_at", "—")

    st.markdown(
        f'<div class="doubao-card"><h4>会话评测结果（session_overall_pass）</h4>'
        f'<p class="doubao-muted">会话 ID：<code>{report.get("session_id", "")}</code> · '
        f"标题：{report.get('session_title', '')}</p>"
        f'<p><span class="{"doubao-pass" if overall else "doubao-fail"}">'
        f'{"✓ 会话质检通过" if overall else "✗ 会话质检未通过"}</span></p>'
        f'<p class="doubao-muted">evaluated_at: {evaluated_at}</p></div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("对话轮次", metrics.get("turn_count", 0))
    c2.metric("作答轮次", metrics.get("answer_turn_count", 0))
    c3.metric("拒答轮次", metrics.get("refuse_turn_count", 0))

    if not report.get("per_turn_results"):
        st.warning("该会话尚无可评测的 user→assistant 轮次。")
        return

    if not overall:
        st.markdown("#### 未达标说明")
        for key, label, thresh in _SESSION_METRIC_SPECS:
            if key not in metrics or metrics[key] is None:
                continue
            val = metrics[key]
            ok = True
            if key == "llm_judge_pass_rate":
                ok = float(val) >= 0.8
            else:
                ok = float(val) >= 1.0
            if not ok:
                st.markdown(f"- **{label}** = {val:.2%}（期望 {thresh}）")

    rows: list[dict[str, str]] = []
    for key, label, thresh in _SESSION_METRIC_SPECS:
        if key not in metrics or metrics[key] is None:
            continue
        val = metrics[key]
        ok = float(val) >= (0.8 if key == "llm_judge_pass_rate" else 1.0)
        rows.append(
            {
                "指标": label,
                "值": f"{float(val):.2%}",
                "阈值": thresh,
                "状态": "达标" if ok else "未达标",
            }
        )
    if rows:
        st.markdown("#### 指标明细")
        st.dataframe(rows, use_container_width=True, hide_index=True)

    per_turn = report.get("per_turn_results", [])
    st.markdown("#### 逐轮结果")
    st.dataframe(per_turn, use_container_width=True, hide_index=True)

    failed = [r for r in per_turn if not r.get("turn_pass", True)]
    if failed:
        with st.expander(f"未通过轮次（{len(failed)}）", expanded=True):
            for r in failed:
                st.markdown(
                    f"**第 {r.get('turn_index')} 轮**：{r.get('question_preview', '')[:80]}…"
                )
                if r.get("llm_judge_reason"):
                    st.caption(r["llm_judge_reason"])

    with st.expander("完整报告 JSON", expanded=False):
        st.json(report)
