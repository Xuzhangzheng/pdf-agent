"""解析预览：结构化块表格展示。"""
from __future__ import annotations

from typing import Any

import streamlit as st


def render_section_divider(title: str, caption: str = "") -> None:
    st.markdown(f'<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown(f"### {title}")
    if caption:
        st.caption(caption)


def render_all_blocks(blocks: list[dict[str, Any]]) -> None:
    """展示全部 block（表格 + 可折叠完整 JSON）。"""
    n = len(blocks)
    render_section_divider(
        f"结构化块明细（共 {n} 条）",
        "Block 为 ingest 阶段的条款/表格/段落单元；Chunks 由 Block 再分块用于检索索引。",
    )

    if not blocks:
        st.info("暂无 blocks 数据。")
        return

    rows: list[dict[str, Any]] = []
    for i, b in enumerate(blocks):
        text = (b.get("text") or "").replace("\n", " ")
        preview = text[:120] + ("…" if len(text) > 120 else "")
        rows.append(
            {
                "#": i + 1,
                "page": b.get("page"),
                "chunk_type": b.get("chunk_type"),
                "clause_id": b.get("clause_id") or "",
                "table_id": b.get("table_id") or "",
                "confidence": b.get("confidence"),
                "text_preview": preview,
            }
        )
    st.dataframe(rows, use_container_width=True, height=480, hide_index=True)

    with st.expander("导出用完整 blocks JSON", expanded=False):
        st.json(blocks)
