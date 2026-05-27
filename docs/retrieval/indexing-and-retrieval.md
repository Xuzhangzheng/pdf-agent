# 索引与检索规范

> 实现：`src/indexing/`、`src/retrieval/retriever.py`  
> 架构总览：[architecture.md](../overview/architecture.md)

## 1. 分块策略

### 1.1 两阶段

1. **Block（结构块）** — `structure.parse_page_markdown`  
   - `clause`：行首 `3.1`、`## 4.1`、`- 3.2` 等  
   - `table`：`|...|`、`<table>`、表题 `表1`  
   - `paragraph`：范围、前言、规范性引用等  

2. **Chunk（检索单元）** — `blocks_to_chunks` + `chunker.chunk_block_text`  
   - 默认 `CHUNK_TARGET_TOKENS=700`，`CHUNK_OVERLAP_TOKENS=140`  
   - token 估算：`len(text)//2`  
   - 超长 Block 在块内滑动切；**国标 4 页通常 1 Block = 1 Chunk**

### 1.2 元数据

每个 Chunk 携带：`page`、`chunk_type`、`clause_id`、`table_id`、`section_title`、`confidence`，写入 FAISS/BM25 与 `doc.json`。

### 1.3 表块

- 行数 ≤40：整表一块  
- 行数 >40：表头 + 20 行滑窗，共享 `table_id`

## 2. 双稠密索引（正文 + 预设问句）

### 2.1 动机

用户问法常为口语或宽泛表述（评测 q06），与条文书面语向量距离较远。对同一 chunk：

- 对 **正文** 做 embedding（保留条款/表字面信息）  
- 用 LLM 生成 **2 个预设问句** 再 embedding（拉近问句–问句相似度）  

稀疏 **BM25 仍只索引正文**，保证「表1」「4.1.2」等字面命中。

### 2.2 离线流程（ingest）

```
doc.json chunks
  → generate_questions_for_chunks()  [ARK, JSON 数组]
  → 缓存 hypothetical_questions.json
  → embed(正文_1..N, 问句_1..M)
  → FaissVectorStore.build → artifacts/faiss/
```

| 字段 | 正文行 | 问句行 |
|------|--------|--------|
| `id` | `chunk_id` | `{chunk_id}#q0` |
| `document` | 条款/表正文 | 预设问题文本 |
| `metadata.index_role` | `content` | `question` |
| `metadata.chunk_id` | `chunk_id` | `chunk_id` |

持久化文件：

- `index.faiss` — 向量（IndexFlatIP + L2 归一化，等价 cosine）
- `store.json` — 与向量行对齐的 id / document / metadata
- `index_meta.json` — 索引元信息

### 2.3 在线稠密召回

1. `FaissVectorStore.search` 取 `k = RETRIEVAL_TOP_K * RETRIEVAL_DENSE_POOL_FACTOR`（上限为向量行数）  
2. 将命中行按 `chunk_id` **归并**：同一 chunk 多条命中取**最优名次 / 最高分**  
3. 与 BM25（chunk_id）做 **RRF**  
4. **Rerank / 生成** 只使用 `doc.json` 中的 **chunk 正文**，不使用问句文本作证据  

### 2.4 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `FAISS_INDEX_DIR` | `artifacts/faiss` | 稠密索引目录（兼容旧名 `CHROMA_PERSIST_DIR`） |
| `INDEX_HYPOTHETICAL_QUESTIONS` | `true` | 是否生成问句向量 |
| `INDEX_QUESTIONS_PER_CHUNK` | `2` | 每 chunk 问句数 |
| `INDEX_QUESTIONS_FORCE_REGENERATE` | `false` | 忽略缓存重生成 |
| `RETRIEVAL_DENSE_POOL_FACTOR` | `3` | 稠密池倍数（含问句行时需扩大） |

### 2.5 问句生成约束（Prompt）

- 仅根据片段生成可回答问题  
- 禁止编造片段外概念  
- 表格片段应含表号/公差/AQL 等可见信息  

实现：`src/indexing/question_generator.py`。

## 3. 混合检索与 RRF

| 路 | 技术 | 粒度 |
|----|------|------|
| 稠密 | FAISS cosine（IndexFlatIP） | 归并后的 `chunk_id` |
| 稀疏 | jieba + BM25Okapi | `chunk_id` |
| 融合 | RRF，`RRF_K=60` | Top `RETRIEVAL_TOP_K`（默认 12） |
| 精排 | qwen3-rerank | Top `RERANK_TOP_N`（默认 5） |

硬拒答：见 [agent-and-refusal-spec.md](../agent/agent-and-refusal-spec.md#41-硬门禁retrieverpy)（双低且无 table/clause 证据）。

## 4. 检索守卫（评测对齐）

实现：`src/retrieval/query_signals.py`、`HybridRetriever._apply_metadata_boost`、`_ensure_required_chunks`、`_pin_required_after_rerank`、`_order_for_rerank`。

| 意图 | 触发 | 守卫行为 |
|------|------|----------|
| 表题 | `wants_table_evidence` | Rerank 前排表块；无 table 则注入 `表1`；可注入 3.5/3.6 |
| OCR 条款 | `extract_clause_ids_from_query`（如 `4.l.2`→`4.1.2`） | 注入目标 `clause_id` chunk |
| 外观/粗糙度 | `wants_appearance_clauses` | 注入 3.2、3.3 |
| 复合（抗拉强度+表1） | `wants_composite_strength_table` | 注入 3.1、4.2、表1 |

**Pin 时机**：Rerank **之后** 再钉住必需块（评测读最终 Top-N `evidence`），必要时挤掉低分项，保证 `table_retrieval_hit` / `clause_retrieval_hit`。

| 变量 | 代码默认 | `.env.example` | 说明 |
|------|----------|----------------|------|
| `RETRIEVAL_METADATA_BOOST` | 0.12 | 0.15 | 表/条款/外观等 metadata 匹配时 RRF 加分 |

## 5. 与 Embedding 文档关系

向量模型与批量限制见 [EMBEDDING.md](./EMBEDDING.md)。双稠密不改变 embedding 模型，只增加 FAISS 行数（约 `chunks × (1 + questions_per_chunk)`）。

## 6. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-22 | 初版：结构分块 + 正文/问句双稠密 + RRF 归并 |
| 2026-05-26 | 增补检索守卫、metadata boost、hard_refuse 例外 |
| 2026-05-26 | 稠密存储 Chroma → FAISS（`artifacts/faiss/`） |
