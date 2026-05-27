# 作业演示录制指南（§四-3）

> 对照 [homework-original-requirements.md](../reference/homework-original-requirements.md) §四（3）与 [submission-checklist.md](./submission-checklist.md)。  
> 建议时长 **5–10 分钟**；可用录屏或按下方清单截屏后拼成 PDF/幻灯片。

## 交付物放置

将录屏或截图放入 [`docs/demo/`](../demo/README.md)（仓库跟踪说明与清单；**截图文件本身可选提交**，避免仓库过大时可单独打包上传作业平台）。

---

## 分镜脚本（约 8 分钟）

| 时间 | 画面 | 操作 / 旁白要点 |
|------|------|-----------------|
| 0:00–1:00 | 终端 | 克隆仓库 → `python3 -m venv .venv` → `source .venv/bin/activate` → `cp .env.example .env`（说明已配置 Key，勿展示明文）→ `bash scripts/fix_mineru_env.sh` |
| 1:00–1:30 | `.env` 片段 | 展示 `PDF_PARSER_BACKEND=mineru`、`INDEX_HYPOTHETICAL_QUESTIONS=true`（可打码 Key） |
| 1:30–4:00 | 终端 ingest | `.venv/bin/python scripts/ingest.py`；说明 MinerU OCR + 结构化入库，非手工录入全文 |
| 4:00–4:45 | Streamlit「解析预览」或 `doc.json` | 展示条款块、**表1**、`quality.passed=true` |
| 4:45–7:30 | Streamlit「问答」 | 按下方 **五题** 依次提问，展示答案、**引用 `[p.N]`**、**verification**（has_evidence / hallucination_risk / should_refuse） |
| 7:30–8:30 | 终端评测 | `pytest tests/ -q` → `.venv/bin/python scripts/evaluate.py` → 展示 `eval_overall_pass=true` 与 `artifacts/eval_report.json` 摘要 |
| 8:30–9:00 | Streamlit「评测报告」 | 打开评测 Tab，与终端结果一致 |

---

## 推荐五题（作业硬性：≥5 问，含 1 表 + 1 无答案）

| 顺序 | 题号 | 问法（可复制） | 展示重点 |
|------|------|----------------|----------|
| 1 | q05 | 本标准对手机蓝牙配对与加密协议有何要求？ | **拒答**；`should_refuse=true` |
| 2 | q03 | 请根据标准中的表格说明键的尺寸、公差或相关参数限值。 | **表1**；引用含 `[p.N 表1]` |
| 3 | q02 | 键的技术要求中，对表面粗糙度或外观质量有哪些规定？ | 条款 3.2/3.3；**勿在答案中展开整张表 1**（易触发 Judge 误杀） |
| 4 | q06 | （使用题库中模糊问法） | 模糊问 → 检索/改写；有依据回答 |
| 5 | q08a | （使用题库中回归/检验问法） | 检验/抽样要点 + 引用 |

完整 9 题见 [`scripts/demo_questions.json`](../../scripts/demo_questions.json)。

---

## 截图清单（§四-3 逐项）

录屏不便时，至少保留以下 **8 张** 截图（文件名建议见 [`docs/demo/screenshots/README.md`](../demo/screenshots/README.md)）：

| # | 文件名建议 | 内容 |
|---|------------|------|
| 1 | `01-setup.png` | 环境安装 / venv / `.env` 配置（Key 打码） |
| 2 | `02-ingest-terminal.png` | `ingest.py` 成功结束 |
| 3 | `03-parse-preview.png` | 解析结果：正文 + **表格**（表1） |
| 4 | `04-qa-table.png` | q03 问答 + 表引用 |
| 5 | `05-qa-refuse.png` | q05 **无答案拒答** + verification |
| 6 | `06-qa-clause.png` | q02 或 q08a + 引用 |
| 7 | `07-self-check.png` | 任一问的 reflection / verification 字段 |
| 8 | `08-evaluate.png` | `evaluate.py` 输出 **`eval_overall_pass=true`** |

---

## Streamlit 启动

```bash
source .venv/bin/activate
streamlit run app/streamlit_app.py
```

浏览器打开后：**入库** → **解析预览** → **问答** → **评测报告**。

---

## 评测未通过时

- `llm_judge_pass_rate` 可能波动，见 [submission-checklist.md](./submission-checklist.md)；优先 **重跑** `evaluate.py`。
- 导出文字版证明：`.venv/bin/python scripts/export_eval_proof.py` → `docs/demo/eval-proof.md`（勿提交含敏感信息的产物）。

---

## 修订

| 日期 | 说明 |
|------|------|
| 2026-05-26 | 初版：对齐作业 §四-3 与 submission-checklist 五题 |
