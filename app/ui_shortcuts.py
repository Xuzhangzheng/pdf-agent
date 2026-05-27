"""缓解 Streamlit 内置快捷键误触（单键 C / Ctrl+C 触发 Clear caches）。"""
from __future__ import annotations

import streamlit as st

_SHORTCUT_GUARD_JS = """
<script>
(function () {
  function isEditable(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea") return true;
    if (el.isContentEditable) return true;
    return !!el.closest("[contenteditable=true]");
  }
  document.addEventListener("keydown", function (e) {
    var k = (e.key || "").toLowerCase();
    if (k !== "c") return;
    if (isEditable(e.target)) return;
    if (e.ctrlKey || e.metaKey) {
      e.stopImmediatePropagation();
      return;
    }
    e.preventDefault();
    e.stopImmediatePropagation();
  }, true);
})();
</script>
"""


def inject_shortcut_guard() -> None:
    st.markdown(_SHORTCUT_GUARD_JS, unsafe_allow_html=True)
