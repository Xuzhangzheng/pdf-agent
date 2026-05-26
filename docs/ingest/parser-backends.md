# PDF 解析后端（可切换）

> 实现：`src/pdf/parsers/factory.py` · 消费方：`src/pdf/structure.py`

## 1. 后端一览

| `PDF_PARSER_BACKEND` | 说明 | 产物目录 |
|----------------------|------|----------|
| `mineru`（默认） | 方案 A：MinerU / magic-pdf OCR | `artifacts/mineru/` |
| `docling` / `scheme_b` | 方案 B：Docling 版面+表格+正文 | `artifacts/docling/{pdf_stem}/` |
| `fusion` / `dual` / `both` | **双通道**：MinerU + Docling 按条款合并 | `artifacts/parsed/fusion/` 报告 |

两条路径在 **structure.py（S1–S6）→ 质量闸门 → 索引** 之后完全一致，仅 **L1 解析** 不同。

### 双通道 fusion（推荐 OCR 仍不稳时）

1. 并行跑 MinerU、Docling（复用各自缓存，除非 `*_FORCE_REPARSE=true`）。
2. 每页按 **条款号** 合并：取更完整/质量更高的一行；仅单通道有的条款（如 MinerU 有 3.7、Docling 无）**交叉补入**。
3. 两通道差异大的条款记入 `fusion_report.json` → `disagreements`。
4. 可选 `OCR_VL_CORRECTION_ENABLED=true`：仅对 **有分歧或缺口** 的页，用方舟 **Responses API**（`doubao-seed-2-0-pro-260215`，`input_image` + `input_text`）对照原图校对（禁止臆造条文）。

## 2. 环境变量

```bash
# 切换解析器（默认 mineru）
PDF_PARSER_BACKEND=mineru
# PDF_PARSER_BACKEND=docling
# PDF_PARSER_BACKEND=scheme_b   # 等同 docling
# PDF_PARSER_BACKEND=fusion

OCR_VL_CORRECTION_ENABLED=false
ARK_VL_MODEL=doubao-seed-2-0-pro-260215

# MinerU（方案 A）
MINERU_OUTPUT_DIR=artifacts/mineru
MINERU_MODEL_MODE=full
MINERU_FORCE_REPARSE=false

# Docling（方案 B）
DOCLING_OUTPUT_DIR=artifacts/docling
DOCLING_FORCE_REPARSE=false

# 两方案共用
OCR_POSTPROCESS_ENABLED=true
```

修改 `PDF_PARSER_BACKEND` 后执行 `python scripts/ingest.py` 重建索引。

## 3. 安装

**方案 A（已有）**

```bash
bash scripts/fix_mineru_env.sh
```

**方案 B（可选）**

```bash
bash scripts/install_docling.sh
```

Docling 体积较大，未安装时设置 `PDF_PARSER_BACKEND=docling` 会提示安装命令。

**首次运行**需从 Hugging Face 下载版面模型（需可访问 `huggingface.co`，或配置镜像 `export HF_ENDPOINT=https://hf-mirror.com`）。模型缓存后可用 `DOCLING_FORCE_REPARSE=false` 复用 `artifacts/docling/{pdf_stem}/`。

## 4. 为何 macOS 上 Docling 中文「全丢」、出现 Ж™# 乱码？

日志里若出现：

```text
Auto OCR model selected ocrmac.
```

说明 Docling 在 **macOS 上自动选了 Apple Vision OCR（ocrmac）**。它面向系统 UI/英文为主，**不擅长国标扫描件里的密集中文**，会把汉字识成西里尔字母、符号、越南语片段等（如 `Ж™1#Д₺`、`bố xố`），看起来像「中文丢了」。

| 对比 | MinerU（方案 A） | Docling 默认（mac auto） |
|------|------------------|---------------------------|
| OCR 引擎 | **PaddleOCR**（中文强） | **ocrmac**（中文弱） |
| 版面/表格 | 中等 | 较强（但 OCR 差则表内也是乱码） |
| 本 PDF 实测 | 中文可读，有错字 | 大量乱码、条款残缺 |

**结论**：不是 Docling「版面能力」没用，而是 **OCR 引擎选错了**。国标 4 页扫描件在本项目里 **优先 `PDF_PARSER_BACKEND=mineru`**。

## 5. Docling 中文扫描件推荐配置

```bash
PDF_PARSER_BACKEND=docling
DOCLING_OCR_ENGINE=rapidocr    # 默认；与 Paddle 系，勿用 auto/ocrmac
DOCLING_FORCE_REPARSE=true     # 换 OCR 引擎后必须重跑
```

可选：`DOCLING_OCR_ENGINE=easyocr`（需 `pip install easyocr`，语言 `ch_sim`）。

首次 `rapidocr` 会下载模型；换引擎后旧 `artifacts/docling/` 缓存会自动失效。

## 6. 选型建议

| 场景 | 建议 |
|------|------|
| 作业演示、已跑通 MinerU | 保持 `mineru` + OCR 后处理 |
| 必须用 Docling | **`DOCLING_OCR_ENGINE=rapidocr`**，勿用默认 auto |
| 表格结构实验 | Docling 表结构 + MinerU OCR 文本（二期融合） |
| macOS 无法 MinerU full | `mineru` lite + 后处理，或 Docling+rapidocr 对比 |

## 7. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-22 | 初版：mineru / docling 可 env 切换 |
| 2026-05-22 | 说明 ocrmac 乱码原因；默认 `DOCLING_OCR_ENGINE=rapidocr` |
| 2026-05-22 | 新增 `fusion` 双通道 + 可选 ARK VL 按页校对 |
| 2026-05-22 | VL 改为方舟 Responses API + `doubao-seed-2-0-pro-260215`；见 [architecture.md](../overview/architecture.md) |

