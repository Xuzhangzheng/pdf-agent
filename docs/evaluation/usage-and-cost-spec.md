# Token 与成本记录规范（Usage & Cost Spec）

> 实现：`src/observability/usage.py`。  
> **出处**：作业 §五-6 工程交付；用户明确要求可审计 Token。

## 1. 记录时机

每次以下调用 **append 一行 JSONL**：

| stage | model 示例 | 触发点 |
|-------|------------|--------|
| `embed` | `text-embedding-v4` | ingest 分批 embed |
| `retrieve_rerank_dashscope` | `qwen3-rerank` | 每轮 retrieve 后 rerank |
| `retrieve_rerank_local` | `bge-reranker-v2-m3` | 降级 rerank |
| `generate` | ARK chat | generate 节点 |
| `reflect` | ARK chat | reflect 节点 |
| `revise` | ARK chat | revise 节点 |
| `rewrite_query` | ARK chat | re_retrieve 改写 |
| `llm_judge` | ARK chat | evaluate.py |

## 2. JSONL 行 Schema

```json
{
  "ts": "2026-05-21T12:00:00+08:00",
  "stage": "reflect",
  "model": "doubao-1-5-lite-32k-250115",
  "prompt_tokens": 1200,
  "completion_tokens": 80,
  "total_tokens": 1280,
  "latency_ms": 890,
  "question_id": "q03_table",
  "retrieval_round": 1,
  "session_id": "uuid"
}
```

- `ask()`：`session_id` 单次问答
- `evaluate.py`：可复用 `session_id=eval-{run_id}`

## 3. 存储路径

```bash
USAGE_LOG_DIR=artifacts/usage
LOG_TOKEN_USAGE=true
```

文件：`artifacts/usage/{session_id}.jsonl`  
汇总：`evaluate.py` → `eval_report.cost_summary`：

```json
{
  "total_tokens": 0,
  "by_stage": { "embed": 0, "generate": 0 },
  "by_model": {},
  "estimated_cost_cny": null
}
```

`estimated_cost_cny`：README 可选配置单价；**不绑定商业报价**。

## 4. Streamlit 展示

- 单次问答：本轮 `total_tokens`、分 stage 条形或表
- 评测页：链接最近一次 `eval_report.cost_summary`

## 5. 预期效果

- 定位成本瓶颈（ingest embed vs 多轮 reflect）
- 演示材料可展示「8 问 + ingest」总 Token
- 客户交付场景可导出审计日志

## 6. 修订记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-05-21 | v1.0 | 计划确认后初版 |
