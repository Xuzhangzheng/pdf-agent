"""会话 Tab：左侧列表 + 右侧聊天（底部固定输入）。"""
from __future__ import annotations

from typing import Any, Callable, Iterator

import streamlit as st

from src.config.settings import Settings


def ensure_session_state() -> None:
    if "chat_session_id" not in st.session_state:
        st.session_state["chat_session_id"] = None
    if "pending_chat" not in st.session_state:
        st.session_state["pending_chat"] = None


def render_session_tab(
    *,
    settings: Settings,
    api_ok: bool,
    index_ready_fn: Callable[[], bool],
    api_get: Callable[[str], Any],
    api_post: Callable[[str, dict | None], Any],
    consume_sse: Callable[[str, str], Iterator[str]],
    langfuse_trace_url: Callable[[str], str | None],
) -> None:
    ensure_session_state()
    st.subheader("多轮会话")
    st.caption(
        f"需先启动 API：`bash scripts/run_api.sh`（`{settings.api_base_url}`）"
        " · Mongo：`bash scripts/start_mongo.sh`"
    )

    if not api_ok:
        return
    if not index_ready_fn():
        st.warning("请先完成 ingest")

    api_base = settings.api_base_url.rstrip("/")
    left, right = st.columns([1, 2.6], gap="medium")

    sessions: list[dict[str, Any]] = []
    with left:
        with st.container(border=True):
            st.markdown("##### 会话列表")
            if st.button("＋ 新建会话", type="primary", use_container_width=True):
                try:
                    s = api_post("/api/sessions", {})
                    st.session_state["chat_session_id"] = s["id"]
                    st.session_state["pending_chat"] = None
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

            try:
                sessions = api_get("/api/sessions")
            except Exception as e:
                st.error(str(e))
                sessions = []

            st.markdown("**历史会话**")
            if not sessions:
                st.caption("暂无会话，点击上方新建。")
            sid = st.session_state.get("chat_session_id")
            for s in sessions:
                sid_item = s.get("id", "")
                title = (s.get("title") or "新会话").strip()
                preview = sid_item[:8] + "…" if len(sid_item) > 8 else sid_item
                label = f"{title}\n{preview}"
                is_active = sid_item == sid
                if st.button(
                    label,
                    key=f"pick_sess_{sid_item}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state["chat_session_id"] = sid_item
                    st.session_state["pending_chat"] = None
                    st.rerun()
            if sid:
                st.caption(f"当前：{sid[:12]}…")
                st.link_button("浏览器聊天页", f"{api_base}/chat", use_container_width=True)

    with right:
        sid = st.session_state.get("chat_session_id")
        if not sid:
            st.markdown(
                '<div class="doubao-card"><p>请在左侧新建或选择会话。</p></div>',
                unsafe_allow_html=True,
            )
            return

        _render_chat_panel(
            sid=sid,
            api_get=api_get,
            consume_sse=consume_sse,
            langfuse_trace_url=langfuse_trace_url,
        )


def _render_chat_panel(
    *,
    sid: str,
    api_get: Callable[[str], Any],
    consume_sse: Callable[[str, str], Iterator[str]],
    langfuse_trace_url: Callable[[str], str | None],
) -> None:
    msgs: list[dict[str, Any]] = []
    try:
        msgs = api_get(f"/api/sessions/{sid}/messages")
    except Exception as e:
        st.error(str(e))

    pending = st.session_state.get("pending_chat")
    pending_q = None
    if pending and pending.get("session_id") == sid:
        pending_q = pending.get("question")

    with st.container(border=True):
        chat_scroll = st.container(height=480, border=False)
        with chat_scroll:
            if not msgs and not pending_q:
                st.markdown(
                    '<p class="doubao-muted">开始提问吧。输入框固定在页面底部。</p>',
                    unsafe_allow_html=True,
                )
            for m in msgs:
                role = m.get("role", "user")
                with st.chat_message("user" if role == "user" else "assistant"):
                    st.markdown(m.get("content", ""))
                    if role == "assistant" and m.get("citations"):
                        with st.expander("引用", expanded=False):
                            st.json(m.get("citations"))

            if pending_q:
                with st.chat_message("user"):
                    st.markdown(pending_q)
                with st.chat_message("assistant"):
                    try:
                        st.write_stream(consume_sse(pending_q, sid))
                        done = st.session_state.get("last_chat_done")
                        if done:
                            if done.get("revised") and done.get("answer") != done.get(
                                "streamed_draft"
                            ):
                                st.markdown(done.get("answer", ""))
                            with st.expander("本轮详情", expanded=False):
                                st.json(
                                    {
                                        "citations": done.get("citations"),
                                        "verification": done.get("verification"),
                                        "trace_id": done.get("trace_id"),
                                    }
                                )
                            tid = done.get("trace_id")
                            if tid:
                                lf = langfuse_trace_url(tid)
                                if lf:
                                    st.markdown(f"[Langfuse Trace]({lf})")
                    except Exception as e:
                        st.error(str(e))
                st.session_state["pending_chat"] = None
                st.rerun()

    q = st.chat_input("输入问题，Enter 发送…", key=f"chat_input_{sid}")
    if q:
        st.session_state["pending_chat"] = {"session_id": sid, "question": q}
        st.rerun()
