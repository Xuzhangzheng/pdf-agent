# Langfuse 自托管观测（企业级方案）

> 实现：`src/observability/langfuse_telemetry.py`、`src/observability/usage.py`（兼容导出）  
> 部署：`deploy/langfuse/docker-compose.yml`、`scripts/start_langfuse.sh`

## 1. 技术选型（2026-05-26 归档）

### 背景

作业与原型期使用 `artifacts/usage/{session_id}.jsonl` 记录 Token，存在：

- 难以跨会话查询、聚合与告警  
- 无 Trace 父子关系（retrieve → generate → reflect 不可视）  
- 不适合企业内网审计、权限与留存  

### 候选方案

| 方案 | 自托管 | 企业适用 | 说明 |
|------|--------|----------|------|
| **Langfuse** | ✅ MIT | ✅ | LLM/Agent 专用：Trace、Generation、评测、Prompt |
| OpenLIT + Grafana | ✅ | ✅ | 偏 OTel + 现有运维栈 |
| Phoenix | ✅ | 中 | 轻量，多租户/告警弱于 Langfuse |
| JSONL 本地文件 | ✅ | ❌ | 已弃用 |

### 决策

采用 **Langfuse v3 自托管** 作为统一观测中间件：

- 一次提问 = 一条 **Trace**（`trace_id` = `session_id`）  
- 各 LLM/Rerank/Embed 调用 = **Generation**（原 `stage` 字段）  
- LangGraph 节点 = **Span**（`graph.retrieve` 等）  
- 评测成本汇总改走 **Langfuse Public API**，不再扫 JSONL 目录  

## 2. 部署（本地 Docker）

推荐随环境一键安装（会尝试启动 Langfuse + MongoDB）：

```bash
bash scripts/setup.sh
```

仅启动中间件（需 Docker 已运行）：

```bash
bash scripts/setup.sh services
# 或
bash scripts/start_langfuse.sh
```

- UI：**http://localhost:3000**  
- 首次启动使用 `deploy/langfuse/.env` 中 `LANGFUSE_INIT_*` 创建管理员（见 `.env.example`）  
- 在 **Settings → API Keys** 创建项目密钥，写入仓库根目录 `.env`：

```bash
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_LOG_IO=true          # 默认记录 Generation/Span 的 input/output
# LANGFUSE_IO_MAX_CHARS=4000  # 单字段截断上限
```

停止栈：

```bash
cd deploy/langfuse && docker compose down
```

生产建议：K8s Helm、修改默认密码、`TELEMETRY_ENABLED=false`（已在 compose 默认关闭外发统计）。

## 3. 应用侧数据模型

```text
Trace (id = session_id)
├── Span: pdf-agent-ask（根）
├── Span: graph.retrieve | graph.generate | graph.reflect | …
├── Generation: embed | retrieve_rerank_dashscope | generate | reflect | …
└── …
```

| 原 JSONL `stage` | Langfuse Generation `name` |
|------------------|----------------------------|
| `embed` | embed |
| `retrieve_rerank_dashscope` | retrieve_rerank_dashscope |
| `generate` / `reflect` / `revise` / `rewrite_query` | 同名 |
| `llm_judge` | llm_judge |
| `ocr_vl_correct` | ocr_vl_correct |

## 4. 代码入口

| 能力 | 函数 |
|------|------|
| 单次问答根 Trace | `query_trace_context()` → `run_query()` |
| LLM Token + I/O | `record_generation()` ← `log_usage()`（`LANGFUSE_LOG_IO=true` 默认开启） |
| 图节点 Span | `span_context()` ← `trace.py` / `retriever` |
| 评测成本汇总 | `summarize_sessions()` ← `summarize_usage()` |
| 刷盘 | `flush_langfuse()` ← `evaluate.py` 结束 |

未配置 Key 时 **静默降级**（`backend: "disabled"`），不影响问答主流程。

### 3.1 Python SDK 版本

应用侧 `langfuse_telemetry.py` 同时兼容：

- **Langfuse 3.x**：`start_as_current_span` / `update_current_trace`
- **Langfuse 4.x**：`start_as_current_observation` / `propagate_attributes`

若 `evaluate.py` 报 `'Langfuse' object has no attribute 'start_as_current_span'`，请拉取最新代码；临时可设 `LANGFUSE_ENABLED=false`。

## 5. 查看与排障

1. 打开 Langfuse UI → **Traces**  
2. 按 `session_id` 或问题文本筛选（UI 链接使用 **32 位 hex trace_id**，由 UUID 去连字符得到）  
3. 展开 Trace 树：节点路径、Generation Token、metadata（`question_id`、`retrieval_round`）  
4. Streamlit **流程调试** Tab 仍保留本地节点摘要；生产以 Langfuse 为准  

### 5.1 自动生成 Markdown 报告

提问后（需 `flush` 或正常结束 `evaluate`）：

```bash
.venv/bin/python scripts/langfuse_session_report.py --session-id <session_id>
# 或最近一条：
.venv/bin/python scripts/langfuse_session_report.py --latest 1
```

输出：`artifacts/langfuse_session_report.md`（执行路径表、节点 I/O 摘要、Token 汇总）。

**说明**：我（Agent）无法实时看你的 Langfuse 浏览器；可通过上述脚本或 Public API 拉取数据。你本地提问后把 `session_id` 发给我，我可帮你解读报告。

## 6. 迁移说明（JSONL → Langfuse）

| 项 | 变更 |
|----|------|
| `artifacts/usage/*.jsonl` | **不再写入**（目录可保留为空） |
| `LOG_TOKEN_USAGE` | 保留字段；实际由 `LANGFUSE_ENABLED` + Keys 控制 |
| `eval_report.cost_summary` | `backend: "langfuse"`，从 API 聚合 |
| 文档 | 本页 + [usage-and-cost-spec.md](../evaluation/usage-and-cost-spec.md) |

## 7. 告警（后续）

可在 Langfuse 配置 Webhook，或将指标导出至 Prometheus/Grafana；见 [scenario-migration.md](../overview/scenario-migration.md) 客户交付一节。

## 修订

| 日期 | 说明 |
|------|------|
| 2026-05-26 | 初版：Langfuse 自托管接入，弃用 usage JSONL |
| 2026-05-27 | 兼容 Langfuse Python SDK 4.x API |
