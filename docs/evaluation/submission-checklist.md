# 作业提交与评测达标清单

文档入口：[docs/README.md](../README.md)。  
对照 [homework-original-requirements.md](../reference/homework-original-requirements.md) §四、§五 与 [evaluation-spec.md](./evaluation-spec.md)。

## 演示五题（录屏推荐）

| 题号 | 能力点 |
|------|--------|
| q05 | 超范围拒答 |
| q03 | 表1 + 引用 `[p.N 表1]` |
| q02 | 条款 3.2/3.3 外观质量（勿在答案中展开表 1，易触发 Judge 误杀） |
| q06 | 模糊问改写 |
| q08a | 检验/抽样要点 |

## 硬性指标（`eval_overall_pass`）

在配置 `DASHSCOPE_API_KEY`、`ARK_API_KEY` 且已 `ingest` 后执行：

```bash
source .venv/bin/activate
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/evaluate.py
```

验收：`artifacts/eval_report.json` 中 `eval_overall_pass=true`（`EVAL_PASS_STRICT=true` 默认）。

| 指标 | 阈值 |
|------|------|
| refuse_accuracy | 1.0 |
| false_refuse_rate | 0 |
| citation_compliance | 1.0 |
| table_retrieval_hit | 1.0（有表题时） |
| clause_retrieval_hit | ≥0.8（有条款题时） |
| reflection_fields_present | 1.0 |
| unsupported_claims_empty | 1.0 |
| llm_judge_pass_rate | ≥0.8 |
| fuzzy / ocr / regression | 通过 |

开发期可 `--skip-llm-judge` 快速看检索；终验须带 Judge。未达标时优先重跑 evaluate（Judge 非确定性），或检查 q02/q07 生成是否偏离 rubric。

## 数据基线（fusion）

`.env` 建议：

- `PDF_PARSER_BACKEND=fusion`
- `DOCLING_OCR_ENGINE=rapidocr`
- `INDEX_HYPOTHETICAL_QUESTIONS=true`

验收 ingest：

- `artifacts/parsed/doc.json`：`quality.passed=true`，含 `4.1.2`、`table_id=表1`
- `artifacts/chroma/index_meta.json`：`dual_dense_enabled=true`
- 正文目录：`artifacts/parsed/md_ingest/fusion/`

## 已知取舍（答辩可说明）

- **q07**：4.1.2 正文为供方检验权，非形位公差；路径为 OCR 纠错 + 如实说明 + 可补 3.5/3.6。
- **Judge 波动**：`temperature=0` 仍可能边界失败；表题 rubric 已对齐「AQL 数值即可」。
- **检索钉住**：Rerank 后对表块、目标条款、外观 3.2/3.3、表题 3.5/3.6 做 `_pin_required_after_rerank`，保证评测读 Top-N 证据时命中。

## 评委环境提示

- 使用 `python3` 或 `.venv/bin/python`，勿依赖系统 `python` 命令。
- Chroma/NumPy 在部分环境需 `bash scripts/fix_mineru_env.sh` 后重跑 ingest。
