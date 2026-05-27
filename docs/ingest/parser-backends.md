# PDF 解析后端（MinerU）

> 实现：`src/pdf/parsers/factory.py` · 消费方：`src/pdf/structure.py`

## 1. 后端

| `PDF_PARSER_BACKEND` | 说明 | 产物目录 |
|----------------------|------|----------|
| `mineru`（唯一） | MinerU / magic-pdf + PaddleOCR | `artifacts/mineru/` |

`docling`、`fusion`、`scheme_b` 等值已在 2026-05 移除；若 `.env` 仍填写旧值，ingest 会报错并提示改为 `mineru`。

**入库正文**以 `artifacts/parsed/md_ingest/mineru/page_*.md` 为准（经 L2 后处理）。该目录在 `artifacts/` 下，**默认被 git 忽略**，本地用 `ls artifacts/parsed/md_ingest/mineru/` 或查看 `artifacts/parsed/doc.json` 中的 `md_ingest_dir` 确认。

**豆包（ARK）不参与 PDF 正文识别**：解析仅 MinerU + 规则后处理；ARK 用于入库后的假设问句、在线问答与反思。可选 VL 校对见下文（当前默认未接入主流程）。

## 2. 环境变量

```bash
PDF_PARSER_BACKEND=mineru

MINERU_OUTPUT_DIR=artifacts/mineru
MINERU_MODEL_MODE=full
MINERU_FORCE_REPARSE=false

OCR_POSTPROCESS_ENABLED=true

# 可选：对低置信/缺口页做 VL 校对（对照页图，禁止臆造条文）
OCR_VL_CORRECTION_ENABLED=false
ARK_VL_MODEL=doubao-seed-2-0-pro-260215
```

修改解析相关配置后执行 `python scripts/ingest.py --force-full` 重建索引。

## 3. 安装

统一入口见 **[setup/environment.md](../setup/environment.md)**：

```bash
bash scripts/setup.sh              # 默认：requirements + MinerU + 尝试 Docker
bash scripts/setup.sh minimal      # 仅 RAG 依赖（已有 artifacts）
bash scripts/setup.sh services     # 仅 MongoDB + Langfuse
```

MinerU 单独修复（NumPy / Paddle / transformers 冲突时）：

```bash
bash scripts/fix_mineru_env.sh
# 仅补 OCR 小文件（大模型已存在时也会执行）：
.venv/bin/python scripts/mineru_ocr_weights.py
```

### 3.1 模型目录

| 路径 | 说明 |
|------|------|
| `artifacts/mineru/models/` | `magic-pdf.json` 的 `models-dir`（含 `MFD/YOLO/yolo_v8_ft.pt` 等） |
| `OCR/paddleocr_torch/ch_PP-OCRv3_det_infer.pth` | magic-pdf **必需**；Kit 全量下载可能漏此文件，需 `mineru_ocr_weights.py` 从 HF 固定 revision 补下 |

`~/magic-pdf.json` 由 `config/magic-pdf.json` 同步，需含 `layout-config.model=doclayout_yolo`（避免默认 layoutlmv3 / detectron2）。

### 3.2 可选 VL 校对（豆包视觉）

`src/pdf/vl_corrector.py` 已实现（`ARK_VL_MODEL` + `/responses` 多模态），但 **`structure.py` 尚未调用**；设 `OCR_VL_CORRECTION_ENABLED=true` 目前不会生效。主流程以 MinerU + `ocr_postprocess.py` 为准。

## 4. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-22 | 初版：mineru / docling 可切换 |
| 2026-05-22 | 新增 fusion 双通道 + 可选 VL |
| 2026-05-26 | **移除 Docling / fusion**；全链路仅 MinerU |
| 2026-05-27 | OCR v3 权重补下脚本；transformers 钉死；澄清 md_ingest 路径与 VL 未接线 |
