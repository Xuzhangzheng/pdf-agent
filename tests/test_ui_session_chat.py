"""会话 Tab：多轮瀑布流与 chat_input 防重复提交（源码级回归）。"""
from __future__ import annotations

import inspect

from app import ui_session


def test_render_chat_panel_shows_history_before_pending() -> None:
    src = inspect.getsource(ui_session._render_chat_panel)
    assert "for m in msgs:" in src
    assert "if pending_q:" in src
    assert "_render_stored_message" in src
    assert "_sync_transcript_cache" in src
    # pending 须在历史消息循环之后渲染
    assert src.index("for m in msgs:") < src.index("if pending_q:")


def test_no_isolated_pending_only_view() -> None:
    assert not hasattr(ui_session, "_run_pending_turn")


def test_chat_input_uses_versioned_key() -> None:
    src = inspect.getsource(ui_session._render_chat_panel)
    assert "_chat_input_widget_key" in src
    assert "_bump_chat_input_version" in src
