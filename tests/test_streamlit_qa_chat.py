"""问答 Tab chat_input 防重复提交：源码级回归。"""
from __future__ import annotations

import inspect

from app import streamlit_app


def test_qa_tab_clears_chat_input_and_regenerates_question_id() -> None:
    src = inspect.getsource(streamlit_app)
    assert 'if not st.session_state.get("qa_pending"):' in src
    assert 'del st.session_state["qa_chat_input"]' in src
    assert 'st.session_state["qa_question_id"] = f"ui-{uuid.uuid4().hex[:8]}"' in src
