# 逻辑调整决策归档（2026-05）

> **范围**：2026-05 下旬针对 Streamlit 多轮、评测通过率、拒答路径、技术条件总览题、会话评测 UI 的一组在线/评测逻辑调整。  
> **原则**：实现以 `src/`、`app/` 为准；本文记录**原因、备选方案、最终决策**及验证方式，供评审与换机复现。  
> **关联规范**：[agent-and-refusal-spec.md](../agent/agent-and-refusal-spec.md)、[indexing-and-retrieval.md](../retrieval/indexing-and-retrieval.md)、[evaluation-spec.md](../evaluation/evaluation-spec.md)、[chat-api.md](../integrations/chat-api.md)。

---

## 变更总览

| 编号 | 主题 | 核心决策 | 主要代码 |
|------|------|----------|----------|
| ADR-01 | Streamlit 多轮问答 | `chat_input` 版本化 key + 提交后清 widget；会话 Tab 先 API 历史再 pending 流 | `app/ui_session.py`、`app/streamlit_app.py` |
| ADR-02 | `eval_overall_pass` 常为 false | 根因多为 Judge 率 &lt;80%；阈值可配置 + rubric/拒答判定统一 | `scripts/evaluate.py`、`src/evaluation/`、`settings.py` |
| ADR-03 | 拒答去关键词捷径 | 无关题走 retrieve→generate→reflect→refuse；逻辑集中到 `refusal.py` | `src/agent/refusal.py`、`query_graph.py` |
| ADR-04 | 「技术条件」回答过简 | 检索钉住范围条+3.1–3.6、英文页眉降权/丢弃、生成总览 hint | `query_signals.py`、`retriever.py`、`structure.py`、`answerer.py` |
| ADR-05 | 会话评测 Tab | `_render_session_eval_report` 显式传入 `settings` | `app/ui_session_eval.py` |

---

## ADR-01：Streamlit 多轮会话与瀑布流展示

### 背景与原因

1. **第二轮仍发送第一轮问题**：Streamlit `st.chat_input` 的 widget state 在 `session_state` 中按 key 持久化；同一会话 ID 下 key 不变时，用户输入框可能保留旧值，提交时读到的是缓存而非新输入。
2. **会话 Tab 多轮不在同一区域展示**：本地 `transcript` 缓存与 API 返回的历史不同步；pending 流式轮次未与已落库消息合并渲染，需切换会话才能看全。

### 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| A. 每次提问后 `st.rerun()` 且依赖默认 `chat_input` key | 改动小 | 无法可靠清空 widget 内部 state | **不采用** |
| B. `chat_input` key 带版本号，提交后 bump 并删除旧 key 条目 | 与 Streamlit 机制对齐，可复现 | 需维护 `_chat_input_ver_{sid}` | **采用** |
| C. 完全不用 `chat_input`，改 `st.text_input` + 按钮 | 行为简单 | UX 差、与官方 chat 模式不一致 | **不采用** |
| D. 仅前端 JS 清输入 | 可能有效 | 不可维护、无官方支持 | **不采用** |

展示层：

| 方案 | 结论 |
|------|------|
| 仅用本地 `transcript` 追加 | 切换会话/刷新后丢消息 → **不采用** |
| `_sync_transcript_cache`：以 API `messages` 为真源，底部再挂 `pending_chat` 流式轮 | **采用** |

### 最终决策

- `chat_input` 使用 `chat_input_{sid}_{ver}`；提交或切换会话后 `_bump_chat_input_version` + `_clear_chat_input_widget_state`。
- 有待处理问题时先消费 SSE，再 `return`，避免同 rerun 内重复提交。
- 问答 Tab 每轮生成独立 `qa_question_id`，避免评测/追踪串题。
- 测试：`tests/test_ui_session_chat.py`、`tests/test_streamlit_qa_chat.py`。

---

## ADR-02：评测 `eval_overall_pass` 与 LLM Judge

### 背景与原因

- 现场多次出现 `eval_overall_pass=false`，排查显示**检索硬性指标（表/条款命中、拒答准确率）通常已达标**，主要短板为 **`llm_judge_pass_rate` &lt; 0.8**（ARK Judge 对措辞、引用格式敏感，同题库重跑有波动）。
- 拒答题与答题的「是否拒答」在 evaluate、会话评测、UI 展示三处判定不一致时，会拉低 `refuse_accuracy` 或误伤 Judge。

### 备选方案

| 方案 | 结论 |
|------|------|
| 降低 `llm_judge_pass_rate` 硬性线为 70% | 与作业「语义正确」预期冲突 → **不采用** |
| 关闭 LLM Judge，仅金标字符串 | 无法覆盖开放表述 → **不采用** |
| 保持 ≥80%，阈值进 `settings.eval_llm_judge_pass_threshold`；统一 `is_refused_state`；微调 rubric/生成提示 | **采用** |
| 扩大题库降低方差 | 作业固定 9 题 → **仅作运维建议** |

### 最终决策

- 默认 `eval_llm_judge_pass_threshold=0.8`（`settings.py`），与 [evaluation-spec.md](../evaluation/evaluation-spec.md) 一致。
- 拒答终态统一用 [`is_refused_state`](../agent/agent-and-refusal-spec.md)（模板 + `verification.should_refuse`），`evaluate.py` 与 `session_eval.py` 共用。
- Judge prompt 强调「仅据 evidence、勿引入证据外事实」；表题/复合题 rubric 与 `demo_questions.json` 对齐 GB/T 1568 正文。
- **运维**：未达标时优先重跑 `evaluate.py`；查 `per_question_results[].llm_judge` 失败题，而非先怀疑全链路检索。

---

## ADR-03：拒答机制去关键词捷径

### 背景与原因

- 早期在 `query_graph` / `stream_query` 用问句关键词（如「蓝牙」「手机」「钢筋混凝土」）直接 `refuse`，虽能让 q05 通过，但：
  - 与作业「Agent 非套壳、可观测链路」不符；
  - 漏判/误判不可解释（真域外词未列出则拒答失败）；
  - 与 Langfuse Trace（retrieve → generate → reflect → refuse）演示路径不一致。
- 用户提供的 [`tests/rejectAnswerExample.txt`](../../tests/rejectAnswerExample.txt)（抗震混凝土等级）要求：**语义无关 + 无可用证据 → 拒答模板**，而非关键词表。

### 备选方案

| 方案 | 结论 |
|------|------|
| A. 扩大关键词黑名单 | 不可穷尽、难迁移 → **不采用** |
| B. 仅 `hard_refuse_gate`（检索双低） | 域外题可能仍生成胡编 → **不采用** |
| C. reflect `should_refuse` + `has_answerable_evidence` 路由 | 可解释、可 Trace → **采用** |
| D. 单独拒答分类模型 | 成本高、MVP 过度 → **不采用** |

### 最终决策

- 新建 [`src/agent/refusal.py`](../../src/agent/refusal.py)：`REFUSE_TEMPLATE`、`route_after_reflect`、`has_answerable_evidence`、`is_refused_state`、`apply_refuse_verification`。
- **删除** `_OUT_OF_SCOPE_MARKERS` / `_is_out_of_scope_question`；q05（蓝牙）与 MongoDB 样例「钢筋水泥」均经检索 + reflect。
- 路由修正：`should_refuse` 且**无**可回答证据 → 直接 `refuse`；不因 `len(evidence)>0` 误进 `revise`（证据块与问题无关时）。
- `answerer.reflect` 提示加强：证据与问题主题不符时应 `should_refuse=true`。
- 测试：`tests/test_refusal_routing.py`；演示说明见 [operations-manual.md](../evaluation/operations-manual.md) q05 行。

---

## ADR-04：「技术条件 / 包含哪些」总览题

### 背景与原因

- 用户会话（如「技术条件具体包含着什么」）在 MongoDB 中仅回答 **5.4 协议条**，而期望为 **范围条（技术要求、验收、标志包装）+ 第 3 章分项**。
- 根因分析：
  1. MinerU 每页英文页眉 `Technical specifications for keys` 与中文「技术条件」向量相近，挤占 Top-5；
  2. 稠密问句索引对宽泛问法友好，但未 pin 第 3 章条款；
  3. 生成提示未区分「总览列举」与「单条协议补充」。

### 备选方案

| 方案 | 结论 |
|------|------|
| A. 仅加长 `max_tokens` | 证据仍只有 5.4 → **不采用** |
| B. 问句关键词映射到固定 chunk_id | 脆弱、难迁移 → **不采用** |
| C. ingest 丢弃英文 boilerplate + 检索降权 + pin 3.1–3.6 + 生成 hint | **采用（组合）** |
| D. 全库重训 embedding | 成本高、MVP 不必要 → **不采用** |

### 最终决策

**信号层**（`query_signals.py`）：

- `wants_technical_requirements_overview`：含「技术条件」「包含什么」等；与 `wants_scope_answer` 有交集时按总览处理。
- `is_english_boilerplate_text`：识别 MinerU 英文页眉。
- `TECH_REQUIREMENTS_CLAUSE_IDS = ("3.1", …, "3.6")`。

**索引层**（`structure.py`）：

- 解析时丢弃 `is_english_boilerplate_text` 块（**需 `ingest --force-full` 才从既有索引清除**；未重建时靠在线降权 + pin）。

**检索层**（`retriever.py`）：

- 总览题 metadata boost（范围条、3.x、`section_title` 含「3技术要求」）；
- 英文块 RRF × 0.05；
- `_pin_technical_overview_chunks`：钉住范围条 + 3.1–3.6（与表题 pin 相同，在 rerank **之后** 注入 Top-N）。

**生成 / 拒答**（`answerer.py`、`refusal.py`）：

- 总览 hint：先范围条，再 3.1–3.6 分项引用；5.4 仅补充；
- `has_answerable_evidence`：总览题若 evidence 含 3.x 或范围条视为可答，避免误拒。

**验证**：

```bash
.venv/bin/python -m pytest tests/test_query_signals.py tests/test_retrieval_technical_overview.py -q
# 索引就绪时检索 Top-5 应为 p.2 范围条 + 3.1–3.4，无英文页眉
```

---

## ADR-05：会话评测 Tab `settings` 未定义

### 背景与原因

- `ui_session_eval.py` 内嵌函数引用 `settings` 未从外层传入，打开 Tab 即 `NameError`。

### 最终决策

- `_render_session_eval_report(..., settings: Settings)` 显式传参；与构建评测 Tab 一致。
- 无架构选型分歧，属缺陷修复。

---

## 验证清单（合并）

| 项 | 命令 / 操作 |
|----|-------------|
| 单元测试 | `.venv/bin/python -m pytest tests/ -q` |
| 9 题评测 | `.venv/bin/python scripts/evaluate.py` → `eval_overall_pass` |
| 技术条件检索 | 见 ADR-04；`tests/test_retrieval_technical_overview.py` |
| 拒答路径 | q05 演示 + `tests/test_refusal_routing.py` |
| Streamlit | 同会话连续两问输入不同文案；会话 Tab 同屏见历史 + 当前流 |
| 索引清英文块 | `ingest.py --force-full`（可选） |

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-27 | 初版：ADR-01～05，原因/方案/决策归档 |
