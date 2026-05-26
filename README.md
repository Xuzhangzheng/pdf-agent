# pdf-agent — 智能文档问答 Agent 原型

**仓库**：https://github.com/Xuzhangzheng/pdf-agent

围绕 **GB/T 1568-2008《键 技术条件》** 扫描版 PDF，实现「解析 → 索引 → 检索 → 生成 → 自检/拒答 → 评测」闭环。

## 架构

- **离线**：`mineru` / `docling` / **`fusion` 双通道** → L2 OCR 规则 → 可选 VL 校对 → `structure.py` 分块与质量闸门 → **正文 + 预设问句双稠密**（Chroma）+ BM25（仅正文）
- **在线**：双稠密归并 + BM25 → **RRF** Top-12 → **qwen3-rerank** Top-5 → metadata boost + **pin 必需块** → ARK 生成 → LangGraph Reflexion（`re_retrieve` ≤1）→ 拒答/引用
- **评测**：`scripts/demo_questions.json`（9 题）+ `scripts/evaluate.py`；`tests/` 单元测试（11 项）
- **审计**：`artifacts/usage/*.jsonl`

**文档地图（推荐）**：[`docs/README.md`](docs/README.md)  
**架构总览**：[`docs/overview/architecture.md`](docs/overview/architecture.md)

## 环境要求

- Python 3.10+（仓库 venv 可能为 3.9，以本机 `.venv` 为准）
- [MinerU / magic-pdf](https://github.com/opendatalab/MinerU)（`mineru` / `fusion` 解析）
- 阿里云百炼 API Key（Embedding + Rerank）
- 火山方舟 ARK API Key（Chat / Judge / Reflection / 可选问句生成）

## 快速开始（评委复现）

**注意**：请逐条执行命令；不要把以 `#` 开头的注释行粘贴进终端。

```bash
git clone https://github.com/Xuzhangzheng/pdf-agent.git
cd pdf-agent
python3 -m venv .venv
source .venv/bin/activate
bash scripts/fix_mineru_env.sh   # 或见下方手动安装
cp .env.example .env             # 填写 DASHSCOPE_API_KEY、ARK_API_KEY
```

**推荐 ingest 配置**（作业数据基线，见 [`docs/evaluation/submission-checklist.md`](docs/evaluation/submission-checklist.md)）：

```bash
# .env 中建议
PDF_PARSER_BACKEND=fusion
DOCLING_OCR_ENGINE=rapidocr
INDEX_HYPOTHETICAL_QUESTIONS=true
```

运行流程（每条单独执行；使用 `.venv/bin/python`）：

```bash
.venv/bin/python scripts/run_mineru_poc.py   # 可选：单独验证 MinerU
.venv/bin/python scripts/ingest.py
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/evaluate.py
streamlit run app/streamlit_app.py
```

**评测验收**：`artifacts/eval_report.json` 中 `eval_overall_pass=true` 表示硬性指标全过。`llm_judge_pass_rate` 可能有波动（≥80% 即达标），未通过时可重跑 evaluate。详见 [`docs/evaluation/submission-checklist.md`](docs/evaluation/submission-checklist.md)。

### MinerU 报错排查（NumPy 2.x）

```bash
source .venv/bin/activate
bash scripts/fix_mineru_env.sh
.venv/bin/python scripts/run_mineru_poc.py
```

PDF 默认路径：`pdf/GBT 1568-2008 键 技术条件.pdf`（4 页）。

### 解析后端

| `PDF_PARSER_BACKEND` | 说明 |
|----------------------|------|
| `mineru` | 代码与 `.env.example` **默认**；MinerU OCR |
| `docling` / `scheme_b` | Docling + `rapidocr`，见 `scripts/install_docling.sh` |
| `fusion` | **推荐（作业达标）**：MinerU+Docling 按条款合并，见 [`docs/ingest/parser-backends.md`](docs/ingest/parser-backends.md) |

修改 `.env` 后重新 `.venv/bin/python scripts/ingest.py`。

## 非套壳说明

1. **文档理解**：`structure.py` 条款/表元数据 + ingest 质量闸门  
2. **检索**：RRF + BM25 + rerank + 表/条款 pin + `re_retrieve`  
3. **可靠性**：LangGraph Reflexion + 拒答链 + `evaluate.py` + Token 审计  

## 配置要点

| 变量 | 说明 |
|------|------|
| `PDF_PARSER_BACKEND` | `mineru`（默认）/ `docling` / `fusion`（推荐 ingest） |
| `INDEX_HYPOTHETICAL_QUESTIONS` | 双稠密问句索引（默认 `true`） |
| `INDEX_QUESTIONS_PER_CHUNK` | 每 chunk 问句数（默认 2） |
| `RETRIEVAL_TOP_K` / `RETRIEVAL_DENSE_POOL_FACTOR` | RRF 池 / 稠密扩大倍数 |
| `RETRIEVAL_METADATA_BOOST` | 代码默认 0.12；`.env.example` 推荐 0.15 |
| `RERANKER_BACKEND` | `dashscope` 或 `local_bge` |
| `MAX_REFLECTION` / `MAX_RE_RETRIEVE` | 默认 2 / 1 |
| `EVAL_PASS_STRICT` / `EVAL_LLM_JUDGE_ENABLED` | 高严格评测 |
| `OCR_VL_CORRECTION_ENABLED` | 可选 VL 校对（默认 `false`） |

完整列表见 [`.env.example`](.env.example) 与 [`src/config/settings.py`](src/config/settings.py)。

## 目录结构

```text
pdf-agent/
├── pdf/
├── scripts/          # ingest, evaluate, demo_questions.json
├── src/
├── tests/            # pytest（query_signals、retriever pin、eval helpers、ark json）
├── app/streamlit_app.py
├── artifacts/        # parsed, chroma, eval_report, usage
└── docs/             # 分目录规范；见 docs/README.md
```

## 文档

- [**文档索引**](docs/README.md)
- [架构](docs/overview/architecture.md) · [解析](docs/ingest/parser-backends.md) · [检索](docs/retrieval/indexing-and-retrieval.md)
- [Agent](docs/agent/agent-and-refusal-spec.md) · [评测](docs/evaluation/evaluation-spec.md) · [提交清单](docs/evaluation/submission-checklist.md)
- [作业原文](docs/reference/homework-original-requirements.md)
- 历史：[archive/](docs/archive/)

## P7 低优先级

全链路通过后，可选 **text/mixed** PDF 分支；主流程以扫描件 + fusion 为准。

## 安全与密钥

- **切勿**将 `.env` 或含真实 API Key 的文件提交到 Git；仓库已通过 `.gitignore` 排除 `.env` 与 `artifacts/`。
- 克隆后执行：`cp .env.example .env`，在本地填写 `DASHSCOPE_API_KEY`、`ARK_API_KEY`（见 [`.env.example`](.env.example)）。
- 提交前可运行：`bash scripts/check_secrets.sh`，扫描是否误将密钥写入将被跟踪的文件。
- 所有云端凭证由 [`src/config/settings.py`](src/config/settings.py) 从环境变量读取，业务代码中无硬编码 Key。
