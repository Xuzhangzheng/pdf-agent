# Agent 与拒答规范（Agent & Refusal Spec）

> 实现：`src/agent/query_graph.py`、`src/agent/orchestrator.py`、`src/retrieval/retriever.py`、`src/generation/answerer.py`。

## 1. LangGraph 节点（一期）

**说明**：精排（qwen3-rerank）在 `HybridRetriever.retrieve()` 内完成，**不是**独立图节点。

```text
retrieve（RRF + rerank + pin 守卫）
  → generate → reflect
  → respond
  → revise → reflect（reflection_count < MAX_REFLECTION）
  → rewrite_query → retrieve（re_retrieve，清空 evidence，round+1）
  → refuse
```

| 节点 | 职责 |
|------|------|
| `retrieve` | 调用 `HybridRetriever`：稠密归并 + BM25 → RRF Top-12 → rerank Top-5 → `_pin_required_after_rerank`；`hard_refuse` 门禁 |
| `generate` | `Answerer.generate_draft`，仅 evidence + `[p.N]` 引用 |
| `reflect` | Self-Reflection JSON（`json_mode`；不支持 `json_object` 的 ARK 模型会自动回退，见 [ARK.md](../integrations/ARK.md)） |
| `revise` | 按 critique 改稿 |
| `rewrite_query` | ARK 改写 query；OCR 题可追加规范化条款号 |
| `respond` / `refuse` | 终态；`respond` 解析引用并补全 citations |

入口：`orchestrator.ask()` → `run_query()`。

## 2. AgentState 字段

`question`, `evidence[]`, `draft_answer`, `final_answer`, `citations[]`, `reflection_notes[]`, `reflection_count`, `re_retrieve_count`, `retrieval_round`, `rewritten_query`, `verification{}`, `hard_refused`

## 3. ReflectionResult（`reflect` 输出）

```json
{
  "has_evidence": true,
  "hallucination_risk": "low|medium|high",
  "should_refuse": false,
  "unsupported_claims": [],
  "missing_citations": [],
  "critique": "",
  "action": "accept|revise|re_retrieve|refuse"
}
```

JSON 解析：`ArkClient.parse_json` 对 LLM 返回中非法反斜杠（如 LaTeX `\geq`）做容错，避免 reflect/judge 崩溃。

### 路由（`route_after_reflect`）

| 条件 | 下一节点 |
|------|----------|
| `hallucination_risk == high` 且无可回答证据 | `refuse` |
| `hallucination_risk == high` 且有 `_has_answerable_evidence` | `revise`（未超 `MAX_REFLECTION`） |
| `should_refuse` 且 `has_answerable_evidence` | `revise` 或最终 `respond` |
| `should_refuse` 且非 `has_answerable_evidence` | `refuse`（检索块与问题无关时） |
| `action == revise` 且未超轮次 | `revise` → `reflect` |
| `action == re_retrieve` 且未超 `MAX_RE_RETRIEVE` | `rewrite_query` → `retrieve` |
| 否则 | `respond` |

`has_answerable_evidence`（[`src/agent/refusal.py`](../../src/agent/refusal.py)）：问句目标条款已在 evidence；或外观题含 3.2/3.3；或表题含 `chunk_type=table`；或技术条件总览题（`wants_technical_requirements_overview`）含 `TECH_REQUIREMENTS_CLAUSE_IDS` 或范围条文本。

去关键词拒答与路由细节见 [logic-adjustments-decision-log.md](../reference/logic-adjustments-decision-log.md#adr-03拒答机制去关键词捷径)。

默认：`MAX_REFLECTION=2`，`MAX_RE_RETRIEVE=1`。

## 4. 拒答优先级

实现集中在 [`src/agent/refusal.py`](../../src/agent/refusal.py)（`REFUSE_TEMPLATE`、`route_after_reflect`、`is_refused_state`）。**无问句关键词捷径**；无关题（如 q05 蓝牙、抗震混凝土）均经检索 + 生成 + reflect 判定。

```text
1. index_missing / ingest_invalid       → refuse
2. post_retrieve: hard_refuse_gate      → refuse（不调 generate）
3. reflect：should_refuse 且非 has_answerable_evidence → refuse（不因 has_ev 块数误 revise）
4. reflect 路由 action=refuse 等        → refuse
5. re_retrieve 用尽仍无可用证据        → refuse
6. 否则 respond（可经 revise）
```

终稿拒答统一为 `REFUSE_TEMPLATE`；`verification.has_evidence` 在拒答时表示证据能否**支撑本题**（非检索块数量）。

### 4.1 硬门禁（`retriever.py`）

```python
hard_refuse = len(evidence) == 0 or (
    max_rrf < RETRIEVAL_MIN_SCORE
    and max_bm25 < BM25_MIN_SCORE
    and not any(e.chunk_type == "table" or e.clause_id for e in evidence)
)
```

有表块或带 `clause_id` 的证据时，不因分数 alone 硬拒（配合 pin 守卫减误拒）。

| 参数 | 代码默认 | 说明 |
|------|----------|------|
| `RETRIEVAL_MIN_SCORE` | 0.35 | RRF 分 |
| `BM25_MIN_SCORE` | 0.0 | 稀疏分 |

### 4.2 `respond` 与 citations

- `_extract_citations`：解析 `[p.N]`、`[p.N 条款x]`、`[p.N 表1]` 及裸 `p.N`
- `_enrich_citations_from_evidence`：表题补 `table_id` 元数据
- 有可回答证据时清空误报的 `unsupported_claims`

## 5. 方案选择说明

采用 **闸门 + Reflexion（≤2 轮）+ 单次 re_retrieve**，满足高严格评测与「Agent 非套壳」演示。

## 6. 修订记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-05-21 | v1.0 | 计划确认后初版 |
| 2026-05-26 | v1.1 | 对齐代码：无 nodes/、rerank 在 retriever、pin/路由/parse_json |
| 2026-05-27 | v1.2 | `refusal.py` 集中拒答；无关键词捷径；总览题 `has_answerable_evidence` |
