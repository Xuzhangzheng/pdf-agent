# 会话 Chat API（SSE + MongoDB）

> 实现：`app/api/`、`src/agent/stream_query.py`、`src/storage/mongo.py`  
> UI：Streamlit「会话」Tab、`http://localhost:8000/chat`

## 启动顺序

```bash
bash scripts/setup.sh            # 一键：Python + 尝试 MongoDB/Langfuse
# 若当时跳过 Docker：bash scripts/setup.sh services
.venv/bin/python scripts/ingest.py   # 修改表格后需重跑 ingest
bash scripts/run_api.sh          # http://127.0.0.1:8000
bash scripts/run_streamlit.sh    # 「会话」Tab
```

详见 [environment.md](../setup/environment.md)。

`.env`：

```bash
API_BASE_URL=http://127.0.0.1:8000
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=pdf_agent
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sessions` | 创建会话 |
| GET | `/api/sessions` | 列表 |
| GET | `/api/sessions/{id}/messages` | 历史消息 |
| POST | `/api/sessions/{id}/chat` | **SSE** 流式问答 |

### SSE 事件

| event | data |
|-------|------|
| `status` | `{"stage":"retrieve\|generate\|reflect\|..."}` |
| `token` | `{"text":"..."}` |
| `done` | `answer`, `citations`, `verification`, `trace_id`, `revised` |
| `error` | `{"message":"..."}` |

## 表格 LaTeX 修复

`src/pdf/table_postprocess.py` 在 ingest 时剥离 `\multicolumn{...}{VALUE}` → `VALUE`。  
**修改后必须重新 ingest**，解析预览中表1 应显示 `1.0`、`2.5` 等数值。

## 流式与终稿

首版在 **generate** 阶段 SSE 输出 token；**reflect/revise** 同步执行。若 `revised=true`，`done.answer` 为终稿，可能与流式草稿不同。

## Streamlit 多轮（ADR-01）

实现：`app/ui_session.py`、`app/streamlit_app.py`。

| 问题 | 对策 |
|------|------|
| 第二轮仍提交第一轮文案 | `chat_input_{sid}_{ver}`，提交后 bump 版本并清除旧 widget state |
| 会话 Tab 历史与当前流割裂 | `_sync_transcript_cache` 以 API 消息为真源，底部追加 `pending_chat` SSE |
| 问答 Tab 题号串扰 | 每轮独立 `qa_question_id` |

详见 [logic-adjustments-decision-log.md](../reference/logic-adjustments-decision-log.md#adr-01streamlit-多轮会话与瀑布流展示)。

## 修订

| 日期 | 说明 |
|------|------|
| 2026-05-26 | 初版 |
| 2026-05-27 | Streamlit 多轮与 transcript 同步（ADR-01） |
