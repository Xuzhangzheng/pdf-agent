# pdf-agent — 智能文档问答 Agent 原型

**仓库**：https://github.com/Xuzhangzheng/pdf-agent

围绕 **GB/T 1568-2008《键 技术条件》** 扫描版 PDF，实现「解析 → 索引 → 检索 → 生成 → 自检/拒答 → 评测」闭环。

## 架构

- **离线**：**MinerU** 扫描解析 → L2 OCR 规则 → 可选 VL 校对 → `structure.py` 分块与质量闸门 → **正文 + 预设问句双稠密**（FAISS）+ BM25（仅正文）
- **在线**：双稠密归并 + BM25 → **RRF** Top-12 → **qwen3-rerank** Top-5 → metadata boost + **pin 必需块** → ARK 生成 → LangGraph Reflexion（`re_retrieve` ≤1）→ 拒答/引用
- **评测**：`scripts/demo_questions.json`（9 题）+ `scripts/evaluate.py`；`tests/` 单元测试（11 项）
- **审计**：**Langfuse** 自托管 Trace（替代 `artifacts/usage/*.jsonl`）

**文档地图（推荐）**：[`docs/README.md`](docs/README.md)  
**架构总览**：[`docs/overview/architecture.md`](docs/overview/architecture.md)

## 环境要求

- **Python 3.10+**（必须；3.9 与 magic-pdf 1.3 不兼容）
- [MinerU / magic-pdf](https://github.com/opendatalab/MinerU)（默认 `setup.sh` 已含；`minimal` 档不含）
- Docker Desktop（推荐；未就绪时可稍后 `bash scripts/setup.sh services`）
- 阿里云百炼 API Key（Embedding + Rerank）
- 火山方舟 ARK API Key（Chat / Judge / Reflection / 可选问句生成）

**换机 / 安装**：见 **[docs/setup/environment.md](docs/setup/environment.md)** — 推荐一条命令 `bash scripts/setup.sh`。

## 快速开始（评委复现）

**注意**：请逐条执行命令；不要把以 `#` 开头的注释行粘贴进终端。

```bash
git clone https://github.com/Xuzhangzheng/pdf-agent.git
cd pdf-agent
bash scripts/setup.sh                       # 完整 Python + 尝试启动 MongoDB/Langfuse
cp .env.example .env                        # 填写 DASHSCOPE_API_KEY、ARK_API_KEY
bash scripts/check_env.sh all
# 评委仅有 artifacts 时: bash scripts/setup.sh minimal
```

**推荐 ingest 配置**（作业数据基线，见 [`docs/evaluation/submission-checklist.md`](docs/evaluation/submission-checklist.md)）：

```bash
# .env 中建议
PDF_PARSER_BACKEND=mineru
INDEX_HYPOTHETICAL_QUESTIONS=true
```

运行流程（每条单独执行；使用 `.venv/bin/python`）：

```bash
.venv/bin/python scripts/ingest.py          # 已有索引可跳过；Chroma 旧索引需 --force-full 重建为 FAISS
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/evaluate.py
bash scripts/run_streamlit.sh               # http://localhost:8501
```

**观测（Langfuse）**：`setup.sh` 会尝试启动；或 `bash scripts/setup.sh services` → UI http://localhost:3000 → API Keys 写入 `.env`。详见 [`docs/integrations/LANGFUSE.md`](docs/integrations/LANGFUSE.md)。

**多轮会话（SSE + MongoDB）**：

```bash
bash scripts/setup.sh services   # 若 Docker 当时未就绪
bash scripts/run_api.sh          # http://127.0.0.1:8000
bash scripts/run_streamlit.sh    # 「会话」Tab
```

详见 [`docs/integrations/chat-api.md`](docs/integrations/chat-api.md) 与 [`docs/setup/environment.md`](docs/setup/environment.md)。表格 LaTeX 修复后请 **重新 ingest**。

**评测验收**：`artifacts/eval_report.json` 中 `eval_overall_pass=true` 表示硬性指标全过。`llm_judge_pass_rate` 可能有波动（≥80% 即达标），未通过时可重跑 evaluate。详见 [`docs/evaluation/submission-checklist.md`](docs/evaluation/submission-checklist.md)。

### MinerU / 环境报错

见 [`docs/setup/environment.md`](docs/setup/environment.md) 第 5 节（含模型已存在仍提示下载、OCR v3 权重、`transformers` 版本、Langfuse SDK 4.x、API IP 限制等）。

```bash
bash scripts/fix_mineru_env.sh
.venv/bin/python scripts/mineru_ocr_weights.py   # 仅补 ch_PP-OCRv3_det 等
pip install -r requirements-mineru.txt --no-deps --force-reinstall
```

仍失败时可：`rm -rf .venv && bash scripts/setup.sh`，再 `bash scripts/check_env.sh all`。

PDF 默认路径：`pdf/GBT 1568-2008 键 技术条件.pdf`（4 页）。

### 解析后端

仅 **MinerU**（`PDF_PARSER_BACKEND=mineru`）。详见 [`docs/ingest/parser-backends.md`](docs/ingest/parser-backends.md)。

修改解析相关配置后重新 `.venv/bin/python scripts/ingest.py --force-full`。

## 非套壳说明

1. **文档理解**：`structure.py` 条款/表元数据 + ingest 质量闸门  
2. **检索**：RRF + BM25 + rerank + 表/条款 pin + `re_retrieve`  
3. **可靠性**：LangGraph Reflexion + 拒答链 + `evaluate.py` + Token 审计  

## 场景与保障（业务迁移）

本题 PoC 为扫描版国标 PDF；向**标准/合规、金融研报、合同、产品手册、客户交付**等场景迁移时，核心链路（解析 → 双稠密索引 → 混合检索 → LangGraph 自检/拒答 → 评测）可复用，差异主要在分块规则、拒答策略与题库配置。

| 场景 | 迁移要点（摘要） |
|------|------------------|
| 标准/合规 | 条款号分块、版本元数据、MinerU 解析（与本题一致） |
| 金融研报 | BM25 实体 + v4 向量 + rerank；调大 `RETRIEVAL_TOP_K` |
| 合同 | 扩展「第 X 条」识别；引用保持条款级 |
| 客户交付 | `artifacts/usage/`、`eval_report.json`、可配置阈值 |

**改配置即可**：解析后端、检索 Top-K、拒答阈值、评测题库。  
**需改模块**：新 PDF 版式解析器、新 `query_signals`、文本层 PDF 直抽（`MVP_FORCE_SCANNED=false` 路径待实现）。

详见 [`docs/overview/scenario-migration.md`](docs/overview/scenario-migration.md)（边界风险与保障表）。

## 演示材料（作业 §四-3）

- **录制脚本与截图清单**：[`docs/evaluation/demo-recording-guide.md`](docs/evaluation/demo-recording-guide.md)
- **截图目录说明**：[`docs/demo/screenshots/`](docs/demo/screenshots/README.md)（可选提交 PNG）
- **评测文字证明**：[`docs/demo/eval-proof.md`](docs/demo/eval-proof.md)（`python3 scripts/export_eval_proof.py` 生成；终验须 `eval_overall_pass=true`）

## 配置要点

| 变量 | 说明 |
|------|------|
| `PDF_PARSER_BACKEND` | `mineru`（唯一） |
| `FAISS_INDEX_DIR` | 稠密向量持久化目录（默认 `artifacts/faiss`） |
| `INDEX_HYPOTHETICAL_QUESTIONS` | 双稠密问句索引（默认 `true`） |
| `INDEX_QUESTIONS_PER_CHUNK` | 每 chunk 问句数（默认 2） |
| `RETRIEVAL_TOP_K` / `RETRIEVAL_DENSE_POOL_FACTOR` | RRF 池 / 稠密扩大倍数 |
| `RETRIEVAL_METADATA_BOOST` | 代码默认 0.12；`.env.example` 推荐 0.15 |
| `RERANKER_BACKEND` | `dashscope` 或 `local_bge` |
| `MAX_REFLECTION` / `MAX_RE_RETRIEVE` | 默认 2 / 1 |
| `EVAL_PASS_STRICT` / `EVAL_LLM_JUDGE_ENABLED` | 高严格评测 |
| `OCR_VL_CORRECTION_ENABLED` | VL 校对开关（实现未接入 ingest，默认 `false`） |
| `ARK_CHAT_JSON_MODE` | 是否强制 `json_object`（部分豆包模型需 `false` 或依赖自动回退） |
| `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | 自托管观测（见 LANGFUSE.md） |

完整列表见 [`.env.example`](.env.example) 与 [`src/config/settings.py`](src/config/settings.py)。

## 目录结构

```text
pdf-agent/
├── pdf/
├── scripts/          # ingest, evaluate, demo_questions.json
├── src/
├── tests/            # pytest（query_signals、retriever pin、eval helpers、ark json）
├── app/streamlit_app.py
├── artifacts/        # parsed, faiss, eval_report, usage
└── docs/             # 分目录规范；demo/ 演示材料；见 docs/README.md
```

## 文档

- [**文档索引**](docs/README.md)
- [架构](docs/overview/architecture.md) · [场景迁移](docs/overview/scenario-migration.md) · [解析](docs/ingest/parser-backends.md) · [检索](docs/retrieval/indexing-and-retrieval.md)
- [Agent](docs/agent/agent-and-refusal-spec.md) · [评测](docs/evaluation/evaluation-spec.md) · [提交清单](docs/evaluation/submission-checklist.md) · [演示录制](docs/evaluation/demo-recording-guide.md)
- [Langfuse 观测](docs/integrations/LANGFUSE.md)
- [作业原文](docs/reference/homework-original-requirements.md)
- 历史：[archive/](docs/archive/)

## P7 低优先级

全链路通过后，可选 **text/mixed** PDF 分支；主流程以扫描件 + MinerU 为准。

## 安全与密钥

- **切勿**将 `.env` 或含真实 API Key 的文件提交到 Git；仓库已通过 `.gitignore` 排除 `.env` 与 `artifacts/`。
- 克隆后执行：`cp .env.example .env`，在本地填写 `DASHSCOPE_API_KEY`、`ARK_API_KEY`（见 [`.env.example`](.env.example)）。
- 提交前可运行：`bash scripts/check_secrets.sh`，扫描是否误将密钥写入将被跟踪的文件。
- 所有云端凭证由 [`src/config/settings.py`](src/config/settings.py) 从环境变量读取，业务代码中无硬编码 Key。
