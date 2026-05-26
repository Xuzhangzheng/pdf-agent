# 评测规范（Evaluation Spec）

> 代码单一事实来源的文字版。实现：`scripts/demo_questions.json`、`scripts/evaluate.py`、`src/evaluation/`。  
> 历史 Baseline 讨论见 [archive/requirements-discussion-log.md](../archive/requirements-discussion-log.md)；冲突时以本 spec 与代码为准。

## 1. 出处与目标

| 出处 | 要求 |
|------|------|
| [homework-original-requirements.md](../reference/homework-original-requirements.md) §四-3 | ≥5 问，含 1 表格 + 1 无答案；引用与自检；评测脚本结果 |
| 同上 §五-3 | 正文、表格、无答案、**模糊问、OCR 错误、回归** |
| 作业第 6 步 | `has_evidence`、`hallucination_risk`、`should_refuse` |

**预期效果**：`.venv/bin/python scripts/evaluate.py` 产出 `artifacts/eval_report.json`；`eval_overall_pass=true` 方可演示/提交（`EVAL_PASS_STRICT=true` 时）。

**注意**：`llm_judge_pass_rate` 依赖 ARK Judge，同一题库重跑可能 75%–87.5% 波动；未达标时可重跑或微调 `demo_questions.json` 中 rubric。

## 2. 题集（`scripts/demo_questions.json`）

**当前 9 题**（MVP 必跑）：

| id | category | expected_behavior |
|----|----------|-------------------|
| q1 | scope | answer |
| q2 | clause | answer |
| q3 | table | answer |
| q4 | composite | answer（抗拉强度+表1，对齐 GB/T 1568 正文） |
| q5 | out_of_scope | refuse |
| q6 | fuzzy | answer |
| q7 | ocr_robust | answer |
| q8a / q8b | regression | answer |

### 2.1 单题 Schema（Pydantic `DemoQuestion`）

```json
{
  "id": "q03_table",
  "question": "……",
  "category": "table",
  "expected_behavior": "answer",
  "must_refuse": false,
  "citation": {
    "min_count": 1,
    "require_page": true,
    "require_table_ref": true
  },
  "retrieval": {
    "must_include_chunk_types": ["table"],
    "min_hits": 1,
    "clause_id_pattern": null
  },
  "answer_gold": {
    "must_contain_any": ["……"],
    "must_not_contain_any": ["……"],
    "numeric_tolerance": null
  },
  "llm_judge": {
    "enabled": true,
    "rubric": "仅根据提供的证据片段，判断回答是否覆盖金标要点，不得引入证据外事实。"
  },
  "regression_group": null,
  "fuzzy_pair_id": null
}
```

| 字段 | 说明 |
|------|------|
| `must_refuse` | `expected_behavior=refuse` 时为 `true` |
| `fuzzy_pair_id` | q6 与清晰版问法共享，用于 `fuzzy_recall_pass` |
| `regression_group` | q8a/q8b 相同 |
| `retrieval.must_include_chunk_types` | 列表中**每一种** `chunk_type` 都须在 Top-K 证据中出现（AND，非 OR） |

### 2.2 题型设计原则

- **fuzzy**：口语/省略问法，检索 Top-5 的 `chunk_id` 集合与清晰版 Jaccard ≥ 0.6
- **ocr_robust**：问句含 OCR 类 typo（如 `4.l.2`），仍须 `retrieval_hit`
- **regression**：两次 `should_refuse` 一致；应答题金标要点 Jaccard ≥ 0.7

## 3. 指标定义（`evaluate.py`）

每题产出 `per_question_results[]`；全局 `metrics` + `eval_overall_pass`。

| 指标 ID | 计算 | MVP 通过线 | 原因 |
|---------|------|------------|------|
| `refuse_accuracy` | 期望拒答题中 `final.verification.should_refuse==true` | **100%** | 无答案硬要求 |
| `false_refuse_rate` | 期望答题误拒比例 | **0%** | 可用性 |
| `citation_compliance` | 答题：`len(citations)>=min` 且每条含 `page` | **100%** | 作业第 5 步 |
| `table_retrieval_hit` | 表题：Top-K 证据含 `chunk_type=table` | **100%** | 表格专项 |
| `clause_retrieval_hit` | 条款题：Top-K 含 `clause_id` 匹配或 BM25 命中条款串 | **≥80%** | POC 后可调 `CLAUSE_HIT_THRESHOLD` |
| `reflection_fields_present` | 含 `has_evidence`,`hallucination_risk`,`should_refuse` | **100%** | 作业第 6 步 |
| `unsupported_claims_empty` | accept 题 `unsupported_claims==[]` | **100%** | 高严格防幻觉 |
| `llm_judge_pass_rate` | `answer_gold` 且 `llm_judge.enabled` 的题 ARK judge `pass` | **≥80%** | 语义正确 |
| `fuzzy_recall_pass` | 见 §2.2 | **通过** | 模糊问 |
| `ocr_robust_pass` | ocr 题 `retrieval_hit` | **通过** | OCR 场景 |
| `regression_consistency` | 见 §2.2 | **通过** | 回归 |
| `rerank_delta_logged` | 每题记录 rerank 前后 top1 `chunk_id` | 信息性 | 检索可解释 |
| `re_retrieve_used_count` | 触发次数 | 信息性 | re_retrieve 链路 |
| `eval_overall_pass` | 上表所有**硬性**指标达标 | **必须** | 演示 §四-3-5 |

`EVAL_PASS_STRICT=true` 时：任一硬性指标失败 → `eval_overall_pass=false`。

## 4. LLM Judge（`src/evaluation/llm_judge.py`）

- 模型：ARK（`ARK_CHAT_MODEL`），`temperature=0`
- 输入：`question`、`evidence[]` 摘要、`final_answer`、`rubric`
- 输出：`{"pass": bool, "reason": str}`
- 仅对 `llm_judge.enabled=true` 的题调用；Token 记入 `usage`（`stage=llm_judge`）

## 5. 报告结构（`artifacts/eval_report.json`）

```json
{
  "run_at": "ISO8601",
  "metrics": { },
  "eval_overall_pass": true,
  "per_question_results": [],
  "cost_summary": { },
  "reranker_degraded": false
}
```

`cost_summary` 字段见 [usage-and-cost-spec.md](./usage-and-cost-spec.md)。

## 6. 修订记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-05-21 | v1.0 | 计划确认后初版：8 题 + 高严格指标 |
| 2026-05-26 | v1.1 | 9 题、must_include_chunk_types AND 语义、Judge 波动说明 |
