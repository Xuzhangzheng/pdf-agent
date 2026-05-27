# Project Work Session Log

> 在实际发生行为时追加一行。起止时间由沟通记录与约定锚点维护。

---

## 记录表

| 日期 | 事项 | 开始时间 | 结束时间 | 时长(分) | 备注 |
|------|------|----------|----------|----------|------|
| 2026-05-21 | 需求沟通阶段（作业解读、方案讨论、需求记录 v1.0–v1.2、Embedding 定稿、`.env`、工期文档） | 17:52 | 19:01 | 69 | 合并原分条记录；时间按你指定 |
| 2026-05-21 | 需求理解与技术实施讨论 | 19:18 | | | 进行中 |
| 2026-05-21 | AI 代码生成及环境配置阶段（项目骨架、MinerU/ingest、OCR 后处理、rerank 端点修复、`.env` 与依赖） | 20:30 | 22:15 | 105 | |
| 2026-05-26 | 评测达标：MinerU 基线、Rerank 后钉住表/条款、双稠密索引、pytest、`eval_overall_pass`；移除 Docling/fusion | | | | 见 `submission-checklist.md` |
| 2026-05-27 | 逻辑调整归档：Streamlit 多轮、Judge 阈值、拒答去关键词、技术条件总览 pin/生成 | | | | [logic-adjustments-decision-log.md](./logic-adjustments-decision-log.md) |
| 2026-05-26 | 文档与代码对齐：`docs/README.md`、规范更新、历史文档迁入 `docs/archive/` | | | | |
| 2026-05-26 | 文档分子目录：overview / ingest / retrieval / agent / evaluation 等 | | | | |
| 2026-05-27 | MinerU 环境排障、ingest/evaluate 修复、依赖锁定与文档同步（见下节） | | | | 代码+文档；见 `environment.md` §5 |

---

## 2026-05-27 工作摘要

### 背景与问题

- 用户本地已有 `artifacts/mineru/models`，但 `ingest.py --force-full` 仍提示下载模型或「未生成 Markdown」。
- `fix_mineru_env.sh` / pip 安装出现大量 NumPy、OpenCV、transformers 冲突警告。
- `evaluate.py` 因 Langfuse SDK 4.x API 变更报错；换 `doubao-seed-2-0-lite` 后假设问句生成报 `json_object` 不支持。
- ingest 建索引阶段曾报 `IP access denied by API-Key restriction`（Embedding Key / IP 白名单）。

### 代码与脚本

| 项 | 说明 |
|----|------|
| **MinerU CLI** | `magic-pdf` 1.3 使用 `-p/-o/-m ocr`；`mineru.py` 区分 v2/legacy，扫描 stderr（exit 0 仍可能失败） |
| **OCR 权重** | 新增 `scripts/mineru_ocr_weights.py`；HF `main` 无 `ch_PP-OCRv3_det_infer.pth`，固定 revision `95b05fd7…` 补下；`download_mineru_models.sh` / `fix_mineru_env.sh` 调用 |
| **运行时依赖** | 新增 `requirements-mineru.txt`：`numpy==1.26.4`、`transformers==4.52.4`、`tokenizers==0.21.1`、`opencv-python-headless==4.10.0.84`；`fix_mineru_env.sh` 多次 `pin_mineru_runtime` + magic-pdf 试跑 |
| **根因（无 Markdown）** | `transformers>=4.54` 导致 UniMERNet `cache_position` / Cache 错误，magic-pdf 静默失败 |
| **ARK** | `ark_client.py`：不支持 `json_object` 的模型自动去掉 `response_format` 重试；`settings.ark_chat_json_mode` |
| **Langfuse** | `langfuse_telemetry.py` 兼容 SDK 3.x（`start_as_current_span`）与 4.x（`start_as_current_observation` / `propagate_attributes`） |
| **FAISS** | （前序）Chroma → `src/indexing/faiss_store.py`，`FAISS_INDEX_DIR` |
| **Docling** | （前序）全链路移除，仅 MinerU |
| **VL 校对** | `vl_corrector.py` 存在但未接入 `structure.py`；文档标明 `OCR_VL_CORRECTION_ENABLED` 当前不生效 |

### 产物与路径澄清

- **入库正文**：`artifacts/parsed/md_ingest/mineru/page_001.md` …（L2 后处理）；`artifacts/` 在 `.gitignore`，IDE 可能不显示。
- **原始 MinerU**：`artifacts/mineru/<书名>/` 或 `magic-pdf/.../ocr/*.md`。
- **索引**：`artifacts/faiss/`、`artifacts/bm25_index.pkl`、`artifacts/parsed/hypothetical_questions.json`。

### 文档同步

- `docs/setup/environment.md` §5 排障表；`parser-backends.md`、`ARK.md`、`LANGFUSE.md`、`architecture.md`、`EMBEDDING.md`、`README.md`、`submission-checklist.md`、`ocr-quality-improvement.md`、`agent-and-refusal-spec.md`、`docs/README.md`、`CLAUDE.md`。

### 建议复现命令

```bash
bash scripts/fix_mineru_env.sh
.venv/bin/python scripts/mineru_ocr_weights.py
.venv/bin/python scripts/ingest.py --force-full
.venv/bin/python scripts/evaluate.py
bash scripts/run_streamlit.sh
```

---

## 填写说明

1. 新阶段（如开发实现）完成时 **追加一行**。
2. **时长** = 结束 − 开始（同日 `HH:MM`）。

---

## 修订

| 日期 | 说明 |
|------|------|
| 2026-05-21 | 简表；助手补全起止时间 |
| 2026-05-21 | 合并为单条「需求沟通阶段」17:52–19:01 |
| 2026-05-21 | 新增「需求理解与技术实施讨论」19:18 起 |
| 2026-05-21 | 新增「AI 代码生成及环境配置阶段」20:30–22:15（105 分） |
| 2026-05-27 | 新增 2026-05-27 工作摘要（MinerU/OCR/transformers/ARK/Langfuse/文档） |
