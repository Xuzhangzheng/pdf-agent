# 环境安装与换机指南

> **目标**：在新机器上用**一条命令**装好 Python 依赖与 Docker 中间件，快速启动 Streamlit、评测、会话 API、Langfuse。  
> **实现**：`scripts/setup.sh`、`scripts/check_env.sh`、`scripts/start_services.sh`

## 1. 前置条件

| 项目 | 要求 |
|------|------|
| 操作系统 | macOS / Linux（Windows 未完整验证） |
| **Python** | **3.10 或 3.11**（必须；3.9 无法运行 magic-pdf 1.3） |
| Docker Desktop | 推荐安装；未就绪时 Python 仍会装好，中间件可稍后补启 |
| 网络 | 百炼、方舟 API；首次 MinerU 可能下载模型 |
| 密钥 | `DASHSCOPE_API_KEY`、`ARK_API_KEY`（`cp .env.example .env`） |

## 2. 一键安装（推荐）

```bash
cd pdf-agent
bash scripts/setup.sh
cp .env.example .env    # 若 setup 未自动创建则手动复制；填写 API Key
bash scripts/check_env.sh all
```

**默认 `setup.sh` 会完成：**

1. 创建/使用 `.venv`（Python 3.10+）
2. `requirements.txt` + MinerU（`fix_mineru_env.sh`）
3. 若缺失则创建 `.env`
4. **若 Docker 已安装且正在运行**：启动 MongoDB + Langfuse  
5. **若 Docker 不可用**：打印提示，**不中断** Python 安装

### 其他命令

| 命令 | 行为 |
|------|------|
| `bash scripts/setup.sh` | **默认**：完整 Python + 尝试 Docker |
| `bash scripts/setup.sh --no-docker` | 完整 Python，不启动 Docker |
| `bash scripts/setup.sh services` | **仅** MongoDB + Langfuse（需 Docker；别名 `docker`） |
| `bash scripts/setup.sh minimal` | 仅 `requirements.txt`（仓库已带 `artifacts/` 时） |
| `bash scripts/setup.sh standard` | 兼容别名：等同 `minimal`（已移除 Docling） |

兼容：`full` 等同默认 Python 部分；`--docker` 已合并进默认，无需再写。

### Docker 未就绪时

终端会看到类似提示：

```text
[跳过] Docker 未安装或未启动，MongoDB / Langfuse 未启动。
如需仅启动中间件，请先安装并启动 Docker Desktop，再执行：
  bash scripts/setup.sh services
```

装好并启动 Docker Desktop 后**只需**执行上述 `services` 命令，**无需**重装 Python。

## 3. 换机快速流程

### 3.1 完整功能（一条命令）

```bash
git clone <repo> && cd pdf-agent
bash scripts/setup.sh
cp .env.example .env
# 填写 DASHSCOPE_API_KEY、ARK_API_KEY
# Langfuse：http://localhost:3000 → Settings → API Keys → 写入 .env

bash scripts/check_env.sh all
```

**启动应用（建议三个终端）：**

```bash
# 若当时 Docker 被跳过，先：bash scripts/setup.sh services

bash scripts/run_api.sh           # http://127.0.0.1:8000
bash scripts/run_streamlit.sh     # http://127.0.0.1:8501
```

| 地址 | 用途 |
|------|------|
| http://localhost:8501 | Streamlit |
| http://localhost:8000/health | Chat API |
| http://localhost:3000 | Langfuse |
| mongodb://localhost:27017 | MongoDB（库名 `pdf_agent`） |

### 3.2 仅演示 RAG（评委 / 已有索引）

```bash
bash scripts/setup.sh minimal
cp .env.example .env
bash scripts/check_env.sh minimal
bash scripts/run_streamlit.sh
```

不需要 MinerU、Docker。仓库需自带 `artifacts/faiss/`（含 `index.faiss`）或自行 ingest。

### 3.3 重建 MinerU 索引

```bash
bash scripts/setup.sh          # 确保含 MinerU
.venv/bin/python scripts/ingest.py --force-full
```

## 4. Docker 中间件

与 `setup.sh` 等价的手动启动：

```bash
bash scripts/setup.sh services
# 或
bash scripts/start_services.sh all
```

- **MongoDB**：`deploy/mongo`，端口 `27017`
- **Langfuse**：`deploy/langfuse`，UI http://localhost:3000（见 [LANGFUSE.md](../integrations/LANGFUSE.md)）

## 5. 版本与兼容

| 组件 | 说明 |
|------|------|
| Python | ≥3.10 |
| NumPy | **1.26.4**（`requirements-mineru.txt` + `fix_mineru_env.sh` 反复锁定；勿被 paddleocr 升到 2.x） |
| OpenCV | **opencv-python-headless 4.10.0.84**（`--no-deps` 安装；勿装会拉高 NumPy 的 `opencv-python` 4.13+） |
| transformers | **4.52.4** + **tokenizers 0.21.1**（magic-pdf 公式识别；≥4.54 会静默失败） |
| magic-pdf | ≥1.2；CLI 为 `magic-pdf -p PDF -o OUT -m ocr` |
| Langfuse Python SDK | **3.x / 4.x 均可**（`langfuse_telemetry.py` 已做 API 兼容） |
| faiss-cpu | 稠密向量索引（`requirements.txt`）；macOS 由 `faiss_store` 自动设置 `NPY_DISABLE_MACOS_ACCELERATE=1` |

### 5.1 MinerU 模型与 ingest 报错

| 现象 | 原因与处理 |
|------|------------|
| 提示「请运行 `download_mineru_models.sh`」但 `yolo_v8_ft.pt` 已有 | magic-pdf 常 **exit 0 但 OCR/公式失败**；不一定是缺整包模型。看 stderr：`cache_position` → 锁定 transformers；缺 `ch_PP-OCRv3_det_infer.pth` → 见下 |
| `ch_PP-OCRv3_det_infer.pth` 404（hf-mirror / main） | HF **main 分支已删该文件**；执行 `bash scripts/fix_mineru_env.sh` 或 `.venv/bin/python scripts/mineru_ocr_weights.py`（固定 commit `95b05fd7…` 补下） |
| `No markdown` / 无 `page_*.md` | 多为 **transformers 过新** 导致 UniMERNet 崩溃；`pip install -r requirements-mineru.txt --no-deps --force-reinstall` 后重跑 ingest |
| IDE 里看不到 `artifacts/parsed/md_ingest/` | `artifacts/` 在 `.gitignore` 中，需在终端 `ls` 或开启「显示忽略文件」；路径见 `doc.json` 的 `md_ingest_dir` |

**脚本**：`scripts/download_mineru_models.sh`（全量 Kit）、`scripts/mineru_ocr_weights.py`（仅补 OCR 小文件）、`scripts/fix_mineru_env.sh`（依赖锁定 + magic-pdf 试跑）。

**产物对照**：

- 原始 MinerU：`artifacts/mineru/<PDF 书名>/` 或 `magic-pdf/.../ocr/*.md`
- **入库正文**：`artifacts/parsed/md_ingest/mineru/page_001.md` …（L2 规则后处理）

### 5.2 pip 依赖冲突黄字

安装 `magic-pdf` / `paddleocr` 时 pip 可能提示 `opencv-python` 未安装或 NumPy 版本冲突。**以 `fix_mineru_env.sh` 结束后的锁定为准**（`requirements-mineru.txt`），不必逐项消掉所有 WARNING。

### 5.3 云端 API

| 现象 | 处理 |
|------|------|
| `IP access denied by API-Key restriction` | 火山/百炼控制台给 API Key **放开当前公网 IP** 或换不限 IP 的 Key；Embedding 用 `DASHSCOPE_*`，Chat 用 `ARK_*`，两把 Key 策略可能不同 |
| `json_object is not supported by this model` | 换 `doubao-seed-*` 等模型时常见；代码会自动去掉 `response_format` 重试，或设 `ARK_CHAT_JSON_MODE=false`（见 [ARK.md](../integrations/ARK.md)） |
| `start_as_current_span`（Langfuse） | 升级代码后已兼容 SDK 4.x；或 `LANGFUSE_ENABLED=false` 跳过观测 |

常见问题：

- **`magic-pdf CLI not found`** → 运行 `bash scripts/setup.sh`（非 `minimal`）  
- **`No such option '--pdf'`** → magic-pdf 1.3+ 已换 CLI；请拉取最新代码并重装依赖  
- **`yolo_v8_ft.pt` 缺失** → `bash scripts/download_mineru_models.sh`（约数 GB，需 HuggingFace）  
- **`paddleocr` / Python 3.9** → 删除 `.venv`，用 3.10+ 重装  
- **会话 Tab 失败** → `bash scripts/setup.sh services` + `bash scripts/run_api.sh`

## 6. 脚本索引

| 脚本 | 作用 |
|------|------|
| **`scripts/setup.sh`** | **一键安装**（默认 all） |
| `scripts/setup.sh services` | 仅 Docker 中间件 |
| `scripts/check_env.sh` | 环境检查（默认 `all`） |
| `scripts/start_services.sh` | 同 `services`（严格需 Docker） |
| `scripts/fix_mineru_env.sh` | MinerU 依赖锁定 + 模型/OCR 检查 + 试跑 |
| `scripts/mineru_ocr_weights.py` | 补全 `ch_PP-OCRv3_det_infer.pth` 等 OCR 权重 |
| `scripts/download_mineru_models.sh` | 下载 PDF-Extract-Kit 全量模型 |
| `requirements-mineru.txt` | MinerU 运行时版本钉（numpy / transformers / opencv） |
| `scripts/run_streamlit.sh` | Streamlit |
| `scripts/run_api.sh` | Chat API |
| `scripts/ingest.py` | 入库（`--force-full` 覆盖重跑） |

## 7. 相关文档

- [parser-backends.md](../ingest/parser-backends.md) — MinerU 解析  
- [chat-api.md](../integrations/chat-api.md) — SSE 会话  
- [LANGFUSE.md](../integrations/LANGFUSE.md) — 观测  
- [submission-checklist.md](../evaluation/submission-checklist.md) — 评测达标
