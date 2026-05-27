# 业务场景迁移与保障

> 对应作业原文 [homework-original-requirements.md](../reference/homework-original-requirements.md) §二-7、§五-4。  
> 本题以 GB/T 1568-2008 扫描国标为 PoC；下列为向合同、金融、合规、客户交付等场景迁移时的**配置级**与**模块级**要点。

## 1. 场景对照

| 场景 | 与 GBT 国标差异 | 迁移要点 |
|------|-----------------|----------|
| **标准 / 合规文件** | 与本题最接近 | 保持条款号分块（`structure.py`）、版本号元数据、拒答模板；`PDF_PARSER_BACKEND=mineru` |
| **金融研报** | 多栏、数字密、公司实体 | 结构分块 + BM25 实体词；Embedding 已用 `text-embedding-v4`；可调 `RERANKER_BACKEND`、加大 `RETRIEVAL_TOP_K` |
| **合同** | 章节 + 定义项 | 扩展条款正则（「第 X 条」「甲方/乙方」）；引用粒度保持条款级 `[p.N 条款]` |
| **产品手册** | 图文多 | MinerU 图注块；二期可选多模态（VL 已预留 `OCR_VL_CORRECTION_ENABLED`） |
| **客户交付** | 审计与可复现 | **Langfuse** Trace、`eval_report.json`、`.env` 配置化阈值、证据链在 `Evidence` / `Citation` |

## 2. 改配置即可 vs 需改模块

| 能力 | 通常仅改配置 | 需改代码 |
|------|--------------|----------|
| 解析后端 | `PDF_PARSER_BACKEND`、MinerU 参数 | 新 PDF 版式解析器 → `src/pdf/parsers/` |
| 分块粒度 | `chunk` 窗口、`structure` 质量门阈值（`settings.py`） | 新文档类型块规则 → `structure.py` |
| 检索强度 | `RETRIEVAL_TOP_K`、`RETRIEVAL_METADATA_BOOST`、`BM25_MIN_SCORE` | 新意图信号 → `query_signals.py` |
| 拒答策略 | `RETRIEVAL_MIN_SCORE`、超范围关键词列表 | 行业合规规则引擎 |
| 评测集 | `scripts/demo_questions.json` | 新 `category` → `evaluation/models.py` |
| 纯文本 PDF | `MVP_FORCE_SCANNED=false`（待实现 pymupdf 路径） | `structure.py` 文本层分支 |

## 3. 边界与保障（通用）

| 边界 | 风险 | 保障 |
|------|------|------|
| 扫描模糊 / 倾斜 | OCR 错字 | `ocr_postprocess`、可选 VL；低置信降权；答案展示原文片段 |
| 表格跨页 / 错行 | 表题答案错 | 表独立 `chunk_type=table`；表题专测；可选 VL 按页校对 |
| 条款号 OCR 错误 | 检索失败 | `query_signals` 归一（如 `4.l.2`→`4.1.2`）；BM25 补召回 |
| 相似条款干扰 | 答非所问 | RRF + rerank + reflect 剔除无依据句 |
| 文档外问题 | 幻觉 | 检索阈值 + 硬拒答 + `should_refuse` |
| API 失败 | 不可用 | 分批 embed、重试；`check_secrets.sh`；ingest 质量闸门 |

## 4. 与本仓库的对应关系

- **自动化保障**：`scripts/evaluate.py` + 9 题 → `eval_overall_pass`；**观测**： [LANGFUSE.md](../integrations/LANGFUSE.md)
- **人工演示保障**：[`docs/evaluation/demo-recording-guide.md`](../evaluation/demo-recording-guide.md)
- **架构细节**：[`architecture.md`](./architecture.md)

## 修订

| 日期 | 说明 |
|------|------|
| 2026-05-26 | 从 archive 计划 §八 提炼为现行 overview 文档 |
