# CLAUDE.md

本仓库为 GB/T 1568-2008 扫描 PDF 的 RAG Agent 原型（解析、双稠密索引、混合检索、LangGraph 反思/拒答、评测）。

## 入口

- 评委复现：根目录 [README.md](README.md)
- 文档地图：[docs/README.md](docs/README.md)
- 配置：`.env.example`、`src/config/settings.py`

## 常用命令

```bash
source .venv/bin/activate
.venv/bin/python scripts/ingest.py
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/evaluate.py
```

推荐 ingest：`PDF_PARSER_BACKEND=mineru`，`INDEX_HYPOTHETICAL_QUESTIONS=true`。MinerU 环境：`bash scripts/fix_mineru_env.sh`；排障见 `docs/setup/environment.md` §5。

## 关键代码

- 解析/分块：`src/pdf/`、`scripts/ingest.py`
- 索引/检索：`src/indexing/faiss_store.py`、`indexer.py`；`src/retrieval/retriever.py`、`query_signals.py`
- Agent：`src/agent/query_graph.py`
- 评测：`scripts/evaluate.py`、`scripts/demo_questions.json`

历史讨论在 `docs/archive/`；现行规范以 `docs/overview/architecture.md` 与代码为准。2026-05 逻辑调整决策见 `docs/reference/logic-adjustments-decision-log.md`。
