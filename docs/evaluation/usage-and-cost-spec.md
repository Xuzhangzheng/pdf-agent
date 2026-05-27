# Token 与成本记录规范（Usage & Cost Spec）

> 实现：`src/observability/langfuse_telemetry.py`（主）、`src/observability/usage.py`（兼容别名）  
> **存储**：Langfuse 自托管（见 [LANGFUSE.md](../integrations/LANGFUSE.md)）  
> **已弃用**：`artifacts/usage/{session_id}.jsonl`

## 1. 记录时机

每次以下调用写入 Langfuse **Generation**：

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
| `ocr_vl_correct` | ARK VL | 可选 VL（`vl_corrector.py` 未接入 ingest，通常无此 Generation） |

## 2. 关联 ID

- `ask()`：`session_id` = Langfuse **trace_id**  
- `evaluate.py`：每题 `session_id`；批次可用 `eval-{run_id}` 作汇总查询  

## 3. 环境变量

```bash
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

部署：`bash scripts/start_langfuse.sh`

## 4. 汇总（`evaluate.py` → `cost_summary`）

`scripts/evaluate.py` 调用 `summarize_usage(session_ids)`，内部请求 Langfuse Public API 按 trace 聚合：

```json
{
  "total_tokens": 0,
  "by_stage": { "generate": 0, "reflect": 0 },
  "by_model": {},
  "estimated_cost_cny": null,
  "backend": "langfuse",
  "langfuse_host": "http://localhost:3000",
  "trace_ids": ["uuid", "eval-..."]
}
```

未配置 Langfuse 时：`backend: "disabled"`，指标为 0。

## 5. 与作业审计的关系

- 评委可在本机启动 Langfuse，复现后于 UI 查看全链路 Token 与节点耗时  
- 不再依赖提交 `artifacts/usage/` 目录（已在 `.gitignore`）

## 修订

| 日期 | 说明 |
|------|------|
| 2026-05-21 | 初版 JSONL |
| 2026-05-26 | 迁移至 Langfuse，弃用 JSONL |
