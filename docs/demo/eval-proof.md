# 评测验收证明（自动生成）

> 由 `scripts/export_eval_proof.py` 从 `artifacts/eval_report.json` 生成。
> **勿**将 API Key 写入本文件。截图演示请对终端 `eval_overall_pass=true` 画面拍照。

**当前快照已达提交线。** 请保留终端截图作为 §四-3 评测证据。

- **run_at**: 2026-05-26T06:28:27.747262+00:00
- **run_id**: eval-c36ef5f8
- **eval_overall_pass**: `True`

## 全局指标

| 指标 | 值 |
|------|-----|
| `citation_compliance` | 1.0 |
| `clause_retrieval_hit` | 1.0 |
| `false_refuse_rate` | 0.0 |
| `fuzzy_recall_pass` | True |
| `llm_judge_pass_rate` | 0.875 |
| `ocr_robust_pass` | True |
| `re_retrieve_used_count` | 0 |
| `reflection_fields_present` | 1.0 |
| `refuse_accuracy` | 1.0 |
| `regression_consistency` | True |
| `table_retrieval_hit` | 1.0 |
| `unsupported_claims_empty` | 1.0 |

## 逐题摘要

| id | judge_pass | should_refuse | citations |
|----|------------|-----------------|-----------|
| q01_scope | True | False | 1 |
| q02_clause | False | False | 2 |
| q03_table | True | False | 2 |
| q04_composite | True | False | 2 |
| q05_out_of_scope | — | True | 0 |
| q06_fuzzy | True | False | 1 |
| q07_ocr_robust | True | False | 1 |
| q08a_regression | True | False | 1 |
| q08b_regression | True | False | 2 |

## 复现命令

```bash
source .venv/bin/activate
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/evaluate.py
.venv/bin/python scripts/export_eval_proof.py
```

作业硬性要求：`eval_overall_pass=true`（含 `llm_judge_pass_rate` ≥ 0.8）。未通过时可重跑 evaluate。
