#!/usr/bin/env python3
"""Streamlit demo: parse preview, Q&A, citations, reflection, usage, flow trace."""
from __future__ import annotations

import json
import logging
import sys
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Literal

import httpx
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.ingest_progress import (
    STEP_MINERU,
    IngestStep,
    ProgressPhase,
    build_ingest_plan,
)
from src.agent.orchestrator import _backend_needs_mineru, ask, ask_with_trace, index_ready, ingest
from src.pdf.parsers.mineru import mineru_cli_available
from src.agent.trace import get_graph_mermaid
from src.config.settings import get_settings
from src.observability.langfuse_telemetry import langfuse_enabled
from src.observability.usage import flush_langfuse, summarize_usage

from app.ui_eval import load_ingest_quality_passed, render_eval_report
from app.ui_parse_preview import render_all_blocks
from app.ui_quality import render_quality_report
from app.ui_session import render_session_tab
from app.ui_session_eval import render_session_eval_tab
from app.ui_theme import inject_doubao_theme

st.set_page_config(
    page_title="pdf-agent",
    layout="wide",
    initial_sidebar_state="collapsed",
)
settings = get_settings()
inject_doubao_theme()


def _langfuse_trace_url(session_id: str) -> str | None:
    from src.observability.langfuse_telemetry import _langfuse_trace_id

    s = settings
    if not langfuse_enabled(s):
        return None
    base = s.langfuse_host.rstrip("/")
    return f"{base}/trace/{_langfuse_trace_id(session_id)}"


def _render_mermaid(code: str, height: int = 420) -> None:
    html = f"""
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <div class="mermaid">{code}</div>
    <script>mermaid.initialize({{ startOnLoad: true, theme: "neutral" }});</script>
    """
    components.html(html, height=height, scrolling=True)


_STEP_ICONS: dict[str, str] = {
    "pending": "○",
    "running": "⏳",
    "done": "✅",
    "error": "❌",
}


class _RingLogHandler(logging.Handler):
    def __init__(self, buf: deque[str], formatter: logging.Formatter) -> None:
        super().__init__()
        self._buf = buf
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buf.append(self.format(record))
        except Exception:
            self.handleError(record)


class _IngestProgressUI:
    """Streamlit 入库进度：步骤清单 + 日志缓冲。"""

    def __init__(
        self,
        plan: list[IngestStep],
        steps_placeholder: Any,
        log_placeholder: Any,
    ) -> None:
        self._plan = plan
        self._steps_ph = steps_placeholder
        self._log_ph = log_placeholder
        self._state: dict[str, Literal["pending", "running", "done", "error"]] = {
            s.id: "pending" for s in plan
        }
        self._detail: dict[str, str] = {}
        self._log_buf: deque[str] = deque(maxlen=80)

    def _refresh_log(self) -> None:
        if self._log_buf:
            self._log_ph.code("\n".join(self._log_buf), language=None)

    def _render_steps(self) -> None:
        lines: list[str] = []
        for i, step in enumerate(self._plan, start=1):
            st_name = self._state.get(step.id, "pending")
            icon = _STEP_ICONS[st_name]
            line = f"{icon} **{i}. {step.label}**"
            detail = self._detail.get(step.id)
            if detail and st_name in ("running", "done", "error"):
                line += f" — _{detail}_"
            elif st_name == "pending":
                line += f" — _{step.hint}_"
            lines.append(line)
            if step.id == STEP_MINERU and st_name == "running":
                lines.append(
                    "  > MinerU 耗时最长，界面可能数十秒无刷新属正常现象。"
                )
        self._steps_ph.markdown("\n\n".join(lines))

    def callback(self, step_id: str, phase: ProgressPhase, detail: str | None = None) -> None:
        if step_id not in self._state:
            return
        if phase == "start":
            self._state[step_id] = "running"
            if detail:
                self._detail[step_id] = detail
        elif phase == "done":
            self._state[step_id] = "done"
            if detail:
                self._detail[step_id] = detail
        elif phase == "error":
            self._state[step_id] = "error"
            if detail:
                self._detail[step_id] = detail
        self._render_steps()
        self._refresh_log()


def _attach_ingest_log_handler(buf: deque[str]) -> logging.Handler:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler = _RingLogHandler(buf, fmt)
    handler.setLevel(logging.INFO)
    for name in ("src.agent", "src.pdf", "src.indexing"):
        log = logging.getLogger(name)
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    return handler


def _detach_ingest_log_handler(handler: logging.Handler) -> None:
    for name in ("src.agent", "src.pdf", "src.indexing"):
        logging.getLogger(name).removeHandler(handler)


def _format_ingest_result(result: dict) -> str:
    parts = [
        f"session: `{result.get('session_id', '')}`",
        f"chunks: **{result.get('chunk_count', 0)}**",
        f"FAISS 行数: **{result.get('vector_row_count', 0)}**",
    ]
    if result.get("question_vector_count"):
        parts.append(f"问句向量: **{result['question_vector_count']}**")
    return " · ".join(parts)


def _node_label(node: str) -> str:
    labels = {
        "retrieve": "检索 retrieve",
        "generate": "生成 generate",
        "reflect": "反思 reflect",
        "revise": "修订 revise",
        "rewrite_query": "改写 query",
        "respond": "回答 respond",
        "refuse": "拒答 refuse",
    }
    return labels.get(node, node)


st.markdown(
    """
<div class="doubao-card app-title-card">
  <span style="font-size: 1.55rem; font-weight: 600; color: #1f2329;">
    智能文档问答
  </span>
  <span style="font-size: 0.9rem; color: #8f959e; margin-left: 0.5rem;">
    GB/T 1568-2008 · MinerU · RAG · LangGraph
  </span>
</div>
""",
    unsafe_allow_html=True,
)

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    [
        "入库",
        "解析预览",
        "问答",
        "会话",
        "流程调试",
        "构建阶段评测报告",
        "会话评测",
    ]
)

with tab1:
    st.subheader("Ingest")
    st.write(f"PDF: `{settings.pdf_input_path}`")
    needs_mineru = _backend_needs_mineru(settings.pdf_parser_backend)
    mineru_ok = mineru_cli_available(settings.mineru_bin, settings.project_root)
    st.caption(
        f"解析后端：`{settings.pdf_parser_backend}`。"
        "点击下方按钮将**完整重跑**解析与索引（强制重跑 MinerU、重生成问句向量、覆盖 FAISS/BM25），"
        "效果等同 `python scripts/ingest.py --force-full`。"
    )
    if needs_mineru and not mineru_ok:
        st.warning(
            "当前未检测到 **magic-pdf**（MinerU）。完整 ingest 前请在终端执行：\n\n"
            "```bash\nbash scripts/setup.sh\n```\n\n"
            "完成后**重启 Streamlit**，再点击按钮。验证：`bash scripts/check_env.sh all`"
        )
    elif needs_mineru:
        st.success("MinerU (magic-pdf) 已就绪，可执行完整 ingest。")

    ingest_plan = build_ingest_plan(settings)
    with st.expander("完整入库流程（与当前配置一致）", expanded=False):
        for i, step in enumerate(ingest_plan, start=1):
            st.markdown(f"{i}. **{step.label}** — {step.hint}")

    if st.button("完整 ingest（覆盖重建）", type="primary", disabled=needs_mineru and not mineru_ok):
        with st.status("完整入库进行中…", expanded=True) as status:
            steps_ph = st.empty()
            with st.expander("运行日志", expanded=True):
                log_ph = st.empty()
            ui = _IngestProgressUI(ingest_plan, steps_ph, log_ph)
            ui._render_steps()
            log_handler = _attach_ingest_log_handler(ui._log_buf)
            try:
                result = ingest(force_full=True, on_progress=ui.callback)
                status.update(label="入库完成", state="complete")
                st.success(_format_ingest_result(result))
                with st.expander("完整结果", expanded=False):
                    st.json(result)
            except Exception as e:
                status.update(label="入库失败", state="error")
                err = str(e)
                st.error(err)
                if "magic-pdf" in err.lower():
                    st.info("请执行 `bash scripts/setup.sh` 后重启 Streamlit。")
                elif "NumPy 2" in err or "_ARRAY_API" in err or "paddleocr" in err.lower():
                    st.warning(
                        "多为 NumPy/OpenCV 版本问题。请在终端执行：\n\n"
                        "`bash scripts/fix_mineru_env.sh`\n\n"
                        "成功后再重试本按钮。"
                    )
            finally:
                _detach_ingest_log_handler(log_handler)
                ui._refresh_log()
    st.info(index_ready() and "索引已就绪" or "索引未就绪，请先 ingest")

with tab2:
    st.subheader("解析预览")
    doc_path = settings.resolve_path(settings.parsed_output_dir) / "doc.json"
    if doc_path.exists():
        data = json.loads(doc_path.read_text(encoding="utf-8"))
        m1, m2, m3 = st.columns(3)
        m1.metric("Chunks", len(data.get("chunks", [])))
        m2.metric(
            "Tables",
            sum(1 for b in data.get("blocks", []) if b.get("chunk_type") == "table"),
        )
        quality = data.get("quality", {})
        m3.metric(
            "质量闸门",
            "通过" if quality.get("passed") else "未通过",
        )
        tables = [b for b in data.get("blocks", []) if b.get("chunk_type") == "table"]
        if tables:
            with st.expander("表格块预览", expanded=False):
                st.markdown(tables[0].get("text", "")[:3000])
        st.markdown("### 质量报告")
        render_quality_report(quality, settings)
        render_all_blocks(data.get("blocks", []))
    else:
        st.warning("未找到 doc.json，请先 ingest")

with tab3:
    st.subheader("单轮问答")
    st.caption("调试检索 + 生成 + 反思；多轮对话请使用「会话」Tab。")
    if not index_ready():
        st.warning("请先完成 ingest")
    else:
        if "qa_messages" not in st.session_state:
            st.session_state["qa_messages"] = []
        if "qa_pending" not in st.session_state:
            st.session_state["qa_pending"] = None
        if "qa_question_id" not in st.session_state:
            st.session_state["qa_question_id"] = f"ui-{uuid.uuid4().hex[:8]}"

        st.caption(f"本页调试 ID（Langfuse）：`{st.session_state['qa_question_id']}`")

        qa_box = st.container(height=420, border=False)
        with qa_box:
            if not st.session_state["qa_messages"] and not st.session_state["qa_pending"]:
                st.markdown(
                    '<p class="doubao-muted">在下方输入问题开始单轮调试。</p>',
                    unsafe_allow_html=True,
                )
            for item in st.session_state["qa_messages"]:
                with st.chat_message(item["role"]):
                    if item["role"] == "assistant":
                        st.markdown(item.get("content", ""))
                        if item.get("extra"):
                            with st.expander("引用 / 自检 / 证据", expanded=False):
                                st.json(item["extra"])
                    else:
                        st.markdown(item.get("content", ""))

            pending_q = st.session_state.get("qa_pending")
            if pending_q:
                with st.chat_message("user"):
                    st.markdown(pending_q)
                with st.chat_message("assistant"):
                    with st.spinner("检索 + 生成 + 反思…"):
                        try:
                            qid = st.session_state["qa_question_id"]
                            state = ask(pending_q, question_id=qid)
                            extra = {
                                "question_id": qid,
                                "citations": state.get("citations", []),
                                "verification": state.get("verification", {}),
                                "reflection_notes": state.get("reflection_notes", []),
                                "evidence": (state.get("evidence", []) or [])[:5],
                            }
                            sid = state.get("session_id")
                            if sid:
                                extra["session_id"] = sid
                                lf_url = _langfuse_trace_url(sid)
                                if lf_url:
                                    extra["langfuse_trace"] = lf_url
                                cost = summarize_usage([sid])
                                flush_langfuse()
                                extra["token_usage"] = cost
                            st.session_state["qa_messages"].append(
                                {"role": "user", "content": pending_q}
                            )
                            st.session_state["qa_messages"].append(
                                {
                                    "role": "assistant",
                                    "content": state.get("final_answer", ""),
                                    "extra": extra,
                                }
                            )
                        except Exception as e:
                            st.session_state["qa_messages"].append(
                                {"role": "user", "content": pending_q}
                            )
                            st.session_state["qa_messages"].append(
                                {"role": "assistant", "content": f"错误：{e}"}
                            )
                st.session_state["qa_pending"] = None
                st.rerun()

        q = st.chat_input("输入问题…", key="qa_chat_input")
        if q:
            st.session_state["qa_pending"] = q
            st.rerun()
        if st.session_state["qa_messages"] and st.button("清空对话", key="qa_clear"):
            st.session_state["qa_messages"] = []
            st.session_state["qa_pending"] = None
            st.session_state["qa_question_id"] = f"ui-{uuid.uuid4().hex[:8]}"
            st.rerun()

def _api_base() -> str:
    return settings.api_base_url.rstrip("/")


def _api_get(path: str) -> Any:
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{_api_base()}{path}")
        r.raise_for_status()
        return r.json()


def _api_post(path: str, body: dict | None = None) -> Any:
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{_api_base()}{path}", json=body or {})
        r.raise_for_status()
        return r.json()


def _consume_sse(question: str, session_id: str):
    """Yield text chunks for st.write_stream."""
    url = f"{_api_base()}/api/sessions/{session_id}/chat"
    draft = ""
    with httpx.Client(timeout=300.0) as client:
        with client.stream(
            "POST",
            url,
            json={"question": question},
            headers={"Accept": "text/event-stream"},
        ) as resp:
            resp.raise_for_status()
            buf = ""
            for chunk in resp.iter_bytes():
                buf += chunk.decode("utf-8", errors="replace")
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    ev, data = "", ""
                    for line in block.split("\n"):
                        if line.startswith("event: "):
                            ev = line[7:].strip()
                        if line.startswith("data: "):
                            data = line[6:]
                    if not data:
                        continue
                    obj = json.loads(data)
                    if ev == "token":
                        draft += obj.get("text", "")
                        yield obj.get("text", "")
                    elif ev == "done":
                        st.session_state["last_chat_done"] = obj
                        if obj.get("revised") and obj.get("answer") != obj.get(
                            "streamed_draft"
                        ):
                            yield "\n\n（已根据自检修订为终稿，见下方详情）\n"


with tab4:
    api_ok = False
    try:
        _api_get("/health")
        api_ok = True
        st.success("Chat API 已连接", icon="✅")
    except Exception as e:
        st.error(f"无法连接 Chat API：{e}")

    render_session_tab(
        settings=settings,
        api_ok=api_ok,
        index_ready_fn=index_ready,
        api_get=_api_get,
        api_post=_api_post,
        consume_sse=_consume_sse,
        langfuse_trace_url=_langfuse_trace_url,
    )

with tab5:
    st.subheader("流程调试（LangGraph 执行追踪）")
    st.caption(
        "展示 Agent 状态机结构与本问实际走过的节点；用于定位检索失败、误拒答、反思循环等问题。"
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.markdown("#### Agent 图结构（静态）")
        try:
            _render_mermaid(get_graph_mermaid())
        except Exception as e:
            st.error(f"无法渲染 Mermaid 图：{e}")

    with col_b:
        st.markdown("#### 本问执行路径（动态）")
        if not index_ready():
            st.warning("请先完成 ingest")
        dq = st.text_input(
            "调试问题",
            value="本标准对手机蓝牙配对与加密协议有何要求？",
            key="trace_q",
        )
        dqid = st.text_input("question_id", value="trace_demo", key="trace_qid")
        if st.button("运行并追踪", key="trace_btn") and dq:
            with st.spinner("执行 LangGraph 并记录节点…"):
                try:
                    state, trace = ask_with_trace(dq, question_id=dqid or None)
                    st.session_state["last_trace"] = trace
                    st.session_state["last_trace_state"] = state
                    st.session_state["last_trace_q"] = dq
                except Exception as e:
                    st.error(str(e))

        trace = st.session_state.get("last_trace")
        state = st.session_state.get("last_trace_state")
        if trace:
            path = " → ".join(_node_label(s["node"]) for s in trace)
            st.success(f"**实际路径**：{path}")
            st.metric("节点数", len(trace))
            if state:
                st.caption(f"session_id: `{state.get('session_id')}`")

            for item in trace:
                node = item["node"]
                summary = item.get("summary", {})
                title = f"Step {item['step']}: {_node_label(node)}"
                with st.expander(title, expanded=(node in ("refuse", "reflect"))):
                    if node == "retrieve":
                        st.write(
                            f"证据块 **{summary.get('evidence_count', 0)}** 个；"
                            f"硬拒答 **{summary.get('hard_refused')}**"
                        )
                        if summary.get("rerank_before_top1"):
                            st.write(
                                f"Rerank Top1: `{summary.get('rerank_before_top1')}` → "
                                f"`{summary.get('rerank_after_top1')}`"
                            )
                    elif node == "reflect":
                        st.write(
                            f"action=`{summary.get('action')}` · "
                            f"risk=`{summary.get('hallucination_risk')}` · "
                            f"should_refuse=`{summary.get('should_refuse')}`"
                        )
                        if summary.get("unsupported_claims"):
                            st.warning(f"unsupported_claims: {summary['unsupported_claims']}")
                        if summary.get("critique_preview"):
                            st.write("critique:", summary["critique_preview"])
                    elif node == "rewrite_query":
                        st.write("改写后 query:", summary.get("rewritten_query"))
                    elif node in ("generate", "revise", "respond", "refuse"):
                        preview = (
                            summary.get("draft_preview")
                            or summary.get("revised_preview")
                            or summary.get("final_preview")
                        )
                        if preview:
                            st.write(preview)
                    st.json(summary)

            if state:
                st.markdown("---")
                st.markdown("#### 终态摘要")
                st.write(state.get("final_answer", ""))
                st.json(state.get("verification", {}))
                sid = state.get("session_id")
                if sid:
                    lf_url = _langfuse_trace_url(sid)
                    if lf_url:
                        st.markdown(f"**Langfuse 完整链路**：[{lf_url}]({lf_url})")
                    flush_langfuse()

with tab6:
    st.subheader("构建阶段评测报告")
    report_path = settings.resolve_path("artifacts/eval_report.json")
    parsed_dir = settings.resolve_path(settings.parsed_output_dir)
    ingest_q = load_ingest_quality_passed(parsed_dir)
    if report_path.exists():
        rep = json.loads(report_path.read_text(encoding="utf-8"))
        render_eval_report(
            rep,
            settings=settings,
            index_ready=index_ready(),
            ingest_quality_passed=ingest_q,
        )
        st.caption("生成报告: `python scripts/evaluate.py`")
    else:
        st.info("运行 `python scripts/evaluate.py` 生成报告")
        if ingest_q is not None:
            st.caption(
                f"当前入库质量闸门 quality.passed = **{'通过' if ingest_q else '未通过'}**"
            )

with tab7:
    api_ok_eval = False
    try:
        _api_get("/health")
        api_ok_eval = True
    except Exception:
        pass
    render_session_eval_tab(
        settings=settings,
        api_ok=api_ok_eval,
        api_get=_api_get,
    )

with st.sidebar:
    st.markdown("### 快捷说明")
    lf_host = settings.langfuse_host if langfuse_enabled(settings) else "（未配置）"
    st.markdown(
        f"""
<div class="doubao-card" style="font-size: 0.88rem;">
<p><b>入库</b>：MinerU 解析 + 索引</p>
<p><b>解析预览</b>：质量报告解读</p>
<p><b>单轮问答</b>：调试 RAG</p>
<p><b>会话</b>：多轮 SSE（需 API）</p>
<p><b>构建阶段评测</b>：9 题 evaluate.py</p>
<p><b>会话评测</b>：历史会话质检</p>
<p><b>Langfuse</b><br/><span class="doubao-muted">{lf_host}</span></p>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption(
        "快捷键：页面焦点下单独按 **C** 可能弹出 Streamlit「Clear caches」；"
        "终端 **Ctrl+C** 会停止服务。本应用已尽量屏蔽误触，复制请用 Ctrl+C 于输入框内。"
    )
