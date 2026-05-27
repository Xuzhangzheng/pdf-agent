# Rerank 规范（Rerank Spec）

> 实现：`src/retrieval/reranker.py`（由 `HybridRetriever.retrieve()` 调用，非独立 LangGraph 节点）。与 [EMBEDDING.md](./EMBEDDING.md) 共用 DashScope 凭证。架构见 [architecture.md](../overview/architecture.md)。

## 1. 选型

| 方案 | 一期角色 |
|------|----------|
| **DashScope `qwen3-rerank`** | **默认主路径** |
| 本地 `BAAI/bge-reranker-v2-m3` | API 失败时可选降级 |
| DeepSeek | **不采用**（无官方 Rerank API） |
| `gte-rerank-v2` | **不采用**（2026-05-30 下线） |

**出处**：[百炼文本排序 API](https://help.aliyun.com/zh/model-studio/text-rerank-api)；作业检索精排需求。

**与 Embedding 分工**：`text-embedding-v4` 召回（FAISS + BM25 + RRF）；`qwen3-rerank` 对 Top-12 精排 → Top-5 进 `generate`。

## 2. 调用标准

| 项 | 值 |
|----|-----|
| 端点 | `POST https://dashscope.aliyuncs.com/compatible-api/v1/reranks` |
| 模型 | `qwen3-rerank` |
| `instruct` | `Given a web search query, retrieve relevant passages that answer the query.` |
| 输入 | `query` + `documents[]`（RRF Top-12 的 `chunk.text`） |
| 输出 | Top-5，按 `relevance_score` 降序 |

### 环境变量

```bash
RERANKER_BACKEND=dashscope
RERANKER_MODEL=qwen3-rerank
RERANK_TOP_N=5
RETRIEVAL_TOP_K=12
RERANKER_INSTRUCT=Given a web search query, retrieve relevant passages that answer the query.
# 降级
RERANKER_BACKEND=local_bge
RERANKER_LOCAL_MODEL=BAAI/bge-reranker-v2-m3
```

## 3. 代码抽象

```python
class RerankerBackend(Protocol):
    def rerank(self, query: str, docs: list[str], top_n: int) -> list[RerankResult]: ...

# RerankResult: index, relevance_score, chunk_id（映射回证据）
```

## 4. 降级链

```text
dashscope 成功 → 使用 API 分数
  ↓ 失败
local_bge（已安装且 RERANKER_BACKEND 允许）→ local_fallback
  ↓ 失败
RRF Top-5 直通；WARN 日志；eval_report.reranker_degraded=true
```

| `reranker_degraded` | 评测 |
|---------------------|------|
| `false` | 正常 |
| `local_fallback` | 注明，不 fail |
| `true` | 醒目 WARN；演示前应修复 |

## 5. 可观测性

- 每题记录 `rerank_before_top1_chunk_id`、`rerank_after_top1_chunk_id`
- `usage`：`stage=retrieve_rerank_dashscope|retrieve_rerank_local`，`model=qwen3-rerank|bge-reranker-v2-m3`

## 6. 修订记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-05-21 | v1.0 | 百炼 qwen3-rerank 为主路径 |
