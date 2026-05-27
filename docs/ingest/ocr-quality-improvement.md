# OCR 质量改进方案（GBT 1568-2008 扫描件）

## 1. 设计原则

- **不做**按文档预置的「条款条文补全」（无法泛化到真实业务）。
- **要做**：识别增强 + 可解释规则纠错 + **缺口检测与降置信度** + 生成/拒答保守。

```text
L0 扫描件 PDF
  ↓
L1 MinerU 解析（magic-pdf + PaddleOCR）
  ↓
L2 规则后处理 ocr_postprocess.py（b/6、±、条款号等，可审计）
  ↓
L4 结构化 + 缺口打标 [OCR缺口] + confidence=low + quality 告警
  ↓
L5 检索/生成/Reflect：证据不足则拒答，不臆造丢失条款；索引可选「正文+预设问句」双稠密（见 [indexing-and-retrieval.md](../retrieval/indexing-and-retrieval.md)）
```

（可选远期：**L-LLM** 仅对单块做「改错字不改义」，默认关闭。）

## 2. L1：识别侧

| 配置 | 说明 |
|------|------|
| `PDF_PARSER_BACKEND=mineru` | 唯一解析后端 |
| `MINERU_MODEL_MODE=full` | Linux 推荐；mac 常回退 lite |
| `MINERU_FORCE_REPARSE=true` | 改 L1 参数后重跑 |
| `OCR_VL_CORRECTION_ENABLED` | 代码在 `vl_corrector.py`；**尚未接入** `structure.py` 主流程（默认关闭） |

## 3. L2：规则后处理

| 规则 | 示例 |
|------|------|
| 键宽 b/6 | `键宽6`→`键宽b`，`6≥8mm`→`b≥8mm`（同段有 `b≤6mm`） |
| 公差符号 | `土AT8`→`±AT8` |
| 条款序列 | `3.键`→`3.1键`（存在 3.2 时） |
| 标准号 | `GB/T11334一2005`→`GB/T11334-2005` |

日志：`artifacts/parsed/ocr_fixes.jsonl`。

## 4. L4：缺口健壮性（不补条文）

当检测到例如 **有 3.6 无 3.7 且孤行「去毛刺」**：

1. 文本打标：`[OCR缺口] …（疑似缺失…，请核对原件）`
2. `doc.json` → `clause_gaps_detected`、`ocr_quality_warnings`
3. 相关块 `confidence=low`，检索/生成应保守或拒答

**不写入**标准原文中不存在的完整 3.7/4.1.2 句子。

## 5. 无法靠规则消除的丢失

整行漏扫只能：**提高 L1（scale/引擎）** 或接受缺口并 **拒答**；禁止用业务外知识库硬填条款。

## 6. 建议操作

```bash
OCR_POSTPROCESS_ENABLED=true
PDF_PARSER_BACKEND=mineru
MINERU_FORCE_REPARSE=true   # 仅改 L1 参数时
python scripts/ingest.py --force-full
```
