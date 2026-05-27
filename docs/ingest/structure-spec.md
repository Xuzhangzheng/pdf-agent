# 结构化解析规范（Structure Spec）

> 实现：`src/pdf/structure.py`。输入：解析后端产出（见 `parser-backends.md`）；输出：`artifacts/parsed/doc.json`。  
> 分块与双稠密索引：见 [indexing-and-retrieval.md](../retrieval/indexing-and-retrieval.md)；总览：[architecture.md](../overview/architecture.md)。

## 1. 输入与健壮性原则

- 默认 PDF：[`pdf/GBT 1568-2008 键 技术条件.pdf`](../../pdf/GBT%201568-2008%20键%20技术条件.pdf)（**4 页**扫描件）
- MVP：`MVP_FORCE_SCANNED=true`，扫描件走 OCR；`PDF_PARSER_BACKEND=mineru`（见 [parser-backends.md](./parser-backends.md)）
- 规则**参数化**（`settings`），便于合同/手册迁移；不以单文档硬编码
- 表格 LaTeX：ingest 时 [`table_postprocess.py`](../../src/pdf/table_postprocess.py) 将 `\multicolumn` 归一化为单元格数值（修改后需重跑 ingest）

**出处**：作业第 2 步（正文、条款、表格）；评审 OCR/表格。

## 2. 块模型

每条 block / chunk 必备字段：

```python
{
  "block_id": str,              # hash(page, seq)
  "chunk_type": "paragraph|clause|table|figure_caption|title|appendix",
  "page": int,                  # 1-based
  "text": str,
  "clause_id": str | null,
  "clause_id_raw": str | null,
  "table_id": str | null,
  "section_title": str | null,
  "parser": "mineru",
  "confidence": "high|medium|low"
}
```

## 3. 提取规则（代码）

| ID | 规则 | 预期效果 |
|----|------|----------|
| **S1** | 行首 `3.1 xxx`；`## 4.1 xxx`；`- 3.2 xxx`（Docling 列表）；OCR 归一 `[lI\|]→1`, `O→0` | 条款号可检索 |
| **S2** | 表题 `表\s*(\d+)` / `Table\s*(\d+)` 绑定 `table_id` | 表题与表体关联 |
| **S3** | MD/HTML 表 → 整表一块；行数>40 → 表头+20 行滑窗，共享 `table_id` | 防超长；表格题可命中 |
| **S4** | 页码优先 MinerU `page_idx`，缺失用 PDF 页序 | 引用含页码 |
| **S5** | 条款匹配但编辑距离>1 → `confidence=low` | OCR 题仍可召回 |
| **S6** | 无法解析条款 → `paragraph`，`clause_id=null`，**不丢文本** | ingest 不中断 |

## 4. Ingest 质量闸门

| 闸门 | GBT MVP 阈值 | 失败 |
|------|--------------|------|
| `pages_parsed` | = PDF 页数 | `IngestError` |
| `total_text_chars` | ≥ `MIN_TOTAL_TEXT_CHARS`（默认 1500） | 阻塞 ingest |
| `table_blocks` | ≥ 1 | **硬失败** |
| `clause_blocks` | ≥ 3 | 硬失败 |
| `parse_coverage` | ≥ 0.95 | 硬失败 |

环境变量：`MIN_TABLE_BLOCKS=1`，`MIN_CLAUSE_BLOCKS=3`，`MIN_PARSE_COVERAGE=0.95`。

**原因**：无表块则无法完成提交要求的表格题；早失败优于 silent 幻觉。

## 5. P0.5 POC 附录（MinerU 实测后填写）

| 项 | 实测值 | 日期 |
|----|--------|------|
| PDF 页数 | 4 | 2026-05-21 |
| `table_blocks` | **1**（`content_list` 中 `type=table` 图像 + MD 中 `![](images/...)`） | 2026-05-21 |
| `clause_blocks` | **9** | 2026-05-21 |
| `total_text_chars` | **~1748** | 2026-05-21 |
| 样例 `clause_id` | _同上_ | — |
| 样例 `table_id` | _同上_ | — |

**POC 前置**：`pip install "magic-pdf[cpu]"`；`~/magic-pdf.json`（`bash scripts/setup_env.sh` 可自动创建）。

## 6. 修订记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-05-21 | v1.0 | 计划确认后初版 |
