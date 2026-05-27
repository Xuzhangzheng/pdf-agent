# 文档索引

> 实现以 [`README.md`](../README.md)、[`src/`](../src/)、[`.env.example`](../.env.example) 为准。  
> 历史讨论见 [`archive/`](./archive/)（非现行规范）。

## 目录结构

```text
docs/
├── README.md                 # 本页（导航）
├── overview/                 # 架构总览
├── ingest/                   # 解析、OCR、分块
├── retrieval/                # 索引、向量、精排
├── agent/                    # LangGraph、拒答、反思
├── evaluation/               # 评测、提交、Token 审计
├── integrations/             # 外部 API（方舟等）
├── reference/                # 作业原文、工时记录
└── archive/                  # 历史计划与需求讨论
```

## setup — 环境与换机

| 文档 | 说明 |
|------|------|
| [environment.md](./setup/environment.md) | **一键安装**、MinerU/transformers/OCR 排障、API Key、版本矩阵 |

## 建议阅读顺序

1. [README.md](../README.md) → [setup/environment.md](./setup/environment.md) → [evaluation/submission-checklist.md](./evaluation/submission-checklist.md)
2. [overview/architecture.md](./overview/architecture.md) → [ingest/parser-backends.md](./ingest/parser-backends.md) → [retrieval/indexing-and-retrieval.md](./retrieval/indexing-and-retrieval.md)
3. [agent/agent-and-refusal-spec.md](./agent/agent-and-refusal-spec.md) → [evaluation/evaluation-spec.md](./evaluation/evaluation-spec.md)

---

## overview — 架构总览

| 文档 | 对应代码 | 何时阅读 |
|------|----------|----------|
| [architecture.md](./overview/architecture.md) | 全链路 | 环境变量、产物目录、端到端数据流 |
| [scenario-migration.md](./overview/scenario-migration.md) | `settings.py`、分块/检索/拒答 | 作业 §五-4 业务场景迁移与边界保障 |

## ingest — 解析与分块

| 文档 | 对应代码 | 何时阅读 |
|------|----------|----------|
| [parser-backends.md](./ingest/parser-backends.md) | `src/pdf/`、`scripts/ingest.py` | MinerU 解析 |
| [ocr-quality-improvement.md](./ingest/ocr-quality-improvement.md) | `ocr_postprocess.py`、`vl_corrector.py` | OCR 规则与可选 VL |
| [structure-spec.md](./ingest/structure-spec.md) | `structure.py`、`chunker.py` | 分块与质量闸门 |

## retrieval — 索引与检索

| 文档 | 对应代码 | 何时阅读 |
|------|----------|----------|
| [indexing-and-retrieval.md](./retrieval/indexing-and-retrieval.md) | `src/indexing/`、`retriever.py` | 双稠密、RRF、pin/boost |
| [EMBEDDING.md](./retrieval/EMBEDDING.md) | DashScope embedding | 向量模型与批量 |
| [rerank-spec.md](./retrieval/rerank-spec.md) | `reranker.py` | qwen3-rerank |

## agent — 在线问答

| 文档 | 对应代码 | 何时阅读 |
|------|----------|----------|
| [agent-and-refusal-spec.md](./agent/agent-and-refusal-spec.md) | `query_graph.py`、`answerer.py` | 反思、拒答、引用 |

## evaluation — 评测与交付

| 文档 | 对应代码 | 何时阅读 |
|------|----------|----------|
| [evaluation-spec.md](./evaluation/evaluation-spec.md) | `evaluate.py`、`demo_questions.json` | 指标与题库 |
| [submission-checklist.md](./evaluation/submission-checklist.md) | `eval_report.json` | 作业达标、演示选题 |
| [demo-recording-guide.md](./evaluation/demo-recording-guide.md) | Streamlit、`evaluate.py` | 作业 §四-3 录屏/截图 |
| [usage-and-cost-spec.md](./evaluation/usage-and-cost-spec.md) | `usage.py` | Token 审计 |

## demo — 演示交付物

| 路径 | 说明 |
|------|------|
| [demo/README.md](./demo/README.md) | 演示材料入口 |
| [demo/eval-proof.md](./demo/eval-proof.md) | 评测验收文字证明（`scripts/export_eval_proof.py`） |
| [demo/screenshots/](./demo/screenshots/README.md) | 截图命名清单 |

## integrations — 外部服务

| 文档 | 对应代码 | 何时阅读 |
|------|----------|----------|
| [ARK.md](./integrations/ARK.md) | `ark_client.py`、`ark_responses.py` | 方舟 Chat / VL |
| [LANGFUSE.md](./integrations/LANGFUSE.md) | `langfuse_telemetry.py` | 自托管 Trace / Token / 节点 Span |
| [chat-api.md](./integrations/chat-api.md) | `app/api/`、`stream_query.py` | SSE 多轮会话 + MongoDB |

## reference — 参考与记录

| 文档 | 说明 |
|------|------|
| [homework-original-requirements.md](./reference/homework-original-requirements.md) | 出题方原文 |
| [project-work-session-log.md](./reference/project-work-session-log.md) | 工时与阶段记录 |

## archive — 历史参考

| 文档 | 说明 |
|------|------|
| [homework-understanding-and-work-plan.md](./archive/homework-understanding-and-work-plan.md) | 早期实施计划 |
| [requirements-discussion-log.md](./archive/requirements-discussion-log.md) | 需求讨论记录 |

文内若与 `overview/architecture.md` 或代码不一致，**以代码为准**。
