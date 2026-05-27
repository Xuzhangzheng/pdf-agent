"""解析质量报告：JSON + 中文解读。"""
from __future__ import annotations

from typing import Any

import streamlit as st

from src.config.settings import Settings, get_settings

_FIELD_LABELS: dict[str, str] = {
    "passed": "闸门总结果",
    "pages_parsed": "已解析页数",
    "total_text_chars": "正文总字符数",
    "table_blocks": "表格块数量",
    "clause_blocks": "条款块数量",
    "parse_coverage": "页覆盖率",
    "errors": "未通过项",
    "ocr_fix_count": "OCR 规则修复次数",
    "md_ingest_dir": "入库 Markdown 目录",
    "clause_gaps_detected": "条款序列疑似缺口",
    "ocr_quality_warnings": "OCR 质量警告",
    "pdf_parser_backend": "解析后端",
    "mineru_model_mode": "MinerU 模式",
    "parser_meta": "解析器元数据",
}


def _threshold_hints(settings: Settings) -> dict[str, str]:
    return {
        "total_text_chars": f"≥ {settings.min_total_text_chars}",
        "table_blocks": f"≥ {settings.min_table_blocks}",
        "clause_blocks": f"≥ {settings.min_clause_blocks}",
        "parse_coverage": f"≥ {settings.min_parse_coverage:.0%}",
        "pages_parsed": "应等于 PDF 总页数（MinerU 合并单 MD 时按全文计）",
    }


def _interpret_metric(key: str, value: Any, settings: Settings) -> str:
    hints = _threshold_hints(settings)
    if key == "passed":
        return "全部闸门通过，可进入索引与问答。" if value else "存在未达标项，ingest 会被阻塞。"
    if key == "parse_coverage" and isinstance(value, (int, float)):
        ok = value >= settings.min_parse_coverage
        return (
            f"{'达标' if ok else '未达标'}（阈值 {hints['parse_coverage']}）。"
            f"表示有文本内容的页数占 PDF 总页数的比例。"
        )
    if key == "total_text_chars" and isinstance(value, int):
        ok = value >= settings.min_total_text_chars
        return (
            f"{'达标' if ok else '未达标'}（{hints['total_text_chars']}）。"
            "全文块字符总和，过低说明 OCR 几乎无输出。"
        )
    if key == "table_blocks" and isinstance(value, int):
        ok = value >= settings.min_table_blocks
        return (
            f"{'达标' if ok else '未达标'}（{hints['table_blocks']}）。"
            "国标题常依赖表块；为 0 时表格类问题无法引用。"
        )
    if key == "clause_blocks" and isinstance(value, int):
        ok = value >= settings.min_clause_blocks
        return (
            f"{'达标' if ok else '未达标'}（{hints['clause_blocks']}）。"
            "识别到条款号结构的块数量。"
        )
    if key == "pages_parsed":
        return f"{hints.get('pages_parsed', '')} 当前值：{value}。"
    if key == "errors" and isinstance(value, list):
        if not value:
            return "无失败项。"
        return "；".join(str(e) for e in value)
    if key == "ocr_fix_count":
        return f"规则后处理自动修正 {value} 处（如 l/I→1、O→0）。"
    if key == "clause_gaps_detected" and value:
        return "条款编号不连续，相关块已降置信度，检索/生成应保守。"
    if key == "ocr_quality_warnings" and value:
        return "；".join(str(w) for w in value) if isinstance(value, list) else str(value)
    if key == "md_ingest_dir":
        return "入库实际使用的 Markdown（含后处理），可与 MinerU 原始缓存对照。"
    if key == "pdf_parser_backend":
        return f"当前为 {value} 单通道解析。"
    return ""


def render_quality_report(quality: dict[str, Any], settings: Settings | None = None) -> None:
    """双栏：解读 + 原始 JSON。"""
    settings = settings or get_settings()
    if not quality:
        st.info("暂无质量报告，请先完成 ingest。")
        return

    passed = quality.get("passed", False)
    st.markdown(
        f'<div class="doubao-card"><h4>总览</h4>'
        f'<span class="{"doubao-pass" if passed else "doubao-fail"}">'
        f'{"✓ 质量闸门通过" if passed else "✗ 质量闸门未通过"}</span>'
        f'<p class="doubao-muted">以下指标来自 <code>doc.json → quality</code>，'
        f"用于判断 OCR/结构化是否达到入库标准。</p></div>",
        unsafe_allow_html=True,
    )

    col_a, col_b = st.columns([1, 1])
    priority = [
        "passed",
        "pages_parsed",
        "parse_coverage",
        "total_text_chars",
        "table_blocks",
        "clause_blocks",
        "ocr_fix_count",
        "clause_gaps_detected",
        "ocr_quality_warnings",
        "errors",
        "pdf_parser_backend",
        "mineru_model_mode",
        "md_ingest_dir",
        "parser_meta",
    ]
    shown = set()
    with col_a:
        st.markdown("#### 字段解读")
        for key in priority:
            if key not in quality:
                continue
            shown.add(key)
            label = _FIELD_LABELS.get(key, key)
            val = quality[key]
            interp = _interpret_metric(key, val, settings)
            with st.expander(f"{label}：{_preview_value(val)}", expanded=key in ("passed", "errors")):
                st.write(interp or "—")
                if key not in ("parser_meta",):
                    st.caption(f"原始值：`{val}`")
        for key, val in quality.items():
            if key in shown:
                continue
            label = _FIELD_LABELS.get(key, key)
            with st.expander(f"{label}：{_preview_value(val)}", expanded=False):
                st.write(_interpret_metric(key, val, settings) or "—")
                st.caption(f"原始值：`{val}`")

    with col_b:
        st.markdown("#### 原始 JSON")
        st.json(quality)


def _preview_value(val: Any, max_len: int = 48) -> str:
    if isinstance(val, bool):
        return "通过" if val else "未通过"
    if isinstance(val, list):
        if not val:
            return "（空）"
        s = ", ".join(str(x) for x in val[:3])
        if len(val) > 3:
            s += f" …共 {len(val)} 项"
        return s[:max_len]
    if isinstance(val, dict):
        return f"{{…{len(val)} 键}}"
    s = str(val)
    return s if len(s) <= max_len else s[: max_len - 1] + "…"
