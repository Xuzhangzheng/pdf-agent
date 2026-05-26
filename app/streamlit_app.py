#!/usr/bin/env python3
"""Streamlit demo: parse preview, Q&A, citations, reflection, usage."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.orchestrator import ask, index_ready, ingest
from src.config.settings import get_settings
from src.observability.usage import summarize_usage

st.set_page_config(page_title="pdf-agent", layout="wide")
settings = get_settings()

st.title("智能文档问答 Agent — GB/T 1568-2008")
st.caption("MinerU + RAG + LangGraph Reflexion + qwen3-rerank")

tab1, tab2, tab3, tab4 = st.tabs(["入库", "解析预览", "问答", "评测报告"])

with tab1:
    st.subheader("Ingest")
    st.write(f"PDF: `{settings.pdf_input_path}`")
    st.caption(
        "首次 ingest 前请在本机终端执行：`bash scripts/fix_mineru_env.sh`（修复 NumPy 2.x 与 Paddle 冲突）"
    )
    if st.button("运行 ingest（MinerU + 索引）"):
        with st.spinner("ingest 中…（MinerU OCR 可能需数分钟）"):
            try:
                result = ingest()
                st.success(result)
            except Exception as e:
                err = str(e)
                st.error(err)
                if "NumPy 2" in err or "_ARRAY_API" in err or "paddleocr" in err.lower():
                    st.warning(
                        "多为 NumPy/OpenCV 版本问题。请在终端执行：\n\n"
                        "`bash scripts/fix_mineru_env.sh`\n\n"
                        "成功后再运行 `python scripts/ingest.py` 或重试本按钮。"
                    )
    st.info(index_ready() and "索引已就绪" or "索引未就绪，请先 ingest")

with tab2:
    st.subheader("解析结果")
    doc_path = settings.resolve_path(settings.parsed_output_dir) / "doc.json"
    if doc_path.exists():
        data = json.loads(doc_path.read_text(encoding="utf-8"))
        st.metric("Chunks", len(data.get("chunks", [])))
        st.metric("Tables", sum(1 for b in data.get("blocks", []) if b.get("chunk_type") == "table"))
        tables = [b for b in data.get("blocks", []) if b.get("chunk_type") == "table"]
        if tables:
            st.markdown("### 表格块预览")
            st.markdown(tables[0].get("text", "")[:3000])
        st.markdown("### 质量报告")
        st.json(data.get("quality", {}))
        with st.expander("全部 blocks"):
            st.json(data.get("blocks", [])[:20])
    else:
        st.warning("未找到 doc.json，请先 ingest")

with tab3:
    st.subheader("问答")
    if not index_ready():
        st.warning("请先完成 ingest")
    q = st.text_input("问题", value="本标准规定了什么范围？")
    qid = st.text_input("question_id（可选）", value="ui_demo")
    if st.button("提问") and q:
        with st.spinner("检索 + 生成 + 反思…"):
            try:
                state = ask(q, question_id=qid or None)
                st.markdown("### 答案")
                st.write(state.get("final_answer", ""))
                st.markdown("### 引用")
                st.json(state.get("citations", []))
                st.markdown("### 自检 (verification)")
                st.json(state.get("verification", {}))
                st.markdown("### 反思记录")
                st.json(state.get("reflection_notes", []))
                st.markdown("### Top 证据")
                st.json(state.get("evidence", [])[:5])
                sid = state.get("session_id")
                if sid:
                    cost = summarize_usage([sid])
                    st.markdown("### Token 用量")
                    st.json(cost)
            except Exception as e:
                st.error(str(e))

with tab4:
    st.subheader("评测报告")
    report_path = settings.resolve_path("artifacts/eval_report.json")
    if report_path.exists():
        rep = json.loads(report_path.read_text(encoding="utf-8"))
        st.metric("eval_overall_pass", rep.get("eval_overall_pass"))
        st.json(rep.get("metrics", {}))
        st.json(rep.get("cost_summary", {}))
        st.dataframe(rep.get("per_question_results", []))
        st.caption("生成报告: `python scripts/evaluate.py`")
    else:
        st.info("运行 `python scripts/evaluate.py` 生成报告")
