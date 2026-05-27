# 演示操作手册

> 按作业五项要求组织的**逐步操作指南**。  
> **推荐阶段顺序**：环境部署 →（可选）MongoDB/Langfuse →（可选）**离线链路**（ingest → pytest → evaluate）→ **Streamlit 交互演示**（解析预览 / 五题问答 / 引用自检；亦可在此完成 ingest、评测）。  
> 分镜与截图命名见 [demo-recording-guide.md](./demo-recording-guide.md)；达标指标见 [submission-checklist.md](./submission-checklist.md)。

**默认 PDF**：`pdf/GBT 1568-2008 键 技术条件.pdf`（4 页扫描件）

> 2026-05 在线/评测逻辑调整（拒答路径、技术条件总览、Streamlit 多轮、`eval_overall_pass` 根因等）见 [logic-adjustments-decision-log.md](../reference/logic-adjustments-decision-log.md)。

---

## 0. 前置条件

| 项目 | 要求 |
|------|------|
| Python | 3.10 或 3.11 |
| 密钥 | `.env` 中配置 `DASHSCOPE_API_KEY`、`ARK_API_KEY` |
| 推荐配置 | `PDF_PARSER_BACKEND=mineru`、`INDEX_HYPOTHETICAL_QUESTIONS=true` |
| Docker | 可选；五项 RAG 演示可不启；需要 Langfuse/会话时在 **Streamlit 前** 执行 `setup.sh services` |

**安全**：录屏/截图时对 API Key 打码，勿展示 `.env` 明文。

---

## 1. 从部署/启动开始的完整流程

对应作业要求 **① 从部署/启动开始**。整体分四段，**后一段不依赖前一段全部完成**（见各段「是否必须」）：

```text
① 环境安装（setup + .env + check_env）
② 可选中间件（MongoDB + Langfuse + API）— 须在 Streamlit 之前
③ 可选离线链路（ingest → pytest → evaluate）— 须在 Streamlit 之前；亦可改在 Streamlit 内完成 ingest / 评测
④ Streamlit 交互演示（§2～§4 证据多在此采集）
```

### 1.1 环境安装

#### 路径 A：完整演示（含 MinerU，推荐提交）

在仓库根目录**逐条**执行（勿整段粘贴带 `#` 的注释行）：

```bash
git clone https://github.com/Xuzhangzheng/pdf-agent.git
cd pdf-agent

bash scripts/setup.sh
cp .env.example .env
# 编辑 .env，填写 DASHSCOPE_API_KEY、ARK_API_KEY

bash scripts/check_env.sh all
```

确认 `.env` 中（可截图，Key 打码）：

```bash
PDF_PARSER_BACKEND=mineru
INDEX_HYPOTHETICAL_QUESTIONS=true
```

#### 路径 B：评委快速路径（仓库已有 `artifacts/`）

```bash
bash scripts/setup.sh minimal
cp .env.example .env
# 填写 DASHSCOPE_API_KEY、ARK_API_KEY

bash scripts/check_env.sh minimal
```

可跳过 [§1.3](#13-可选离线链路ingest--pytest--evaluate) 中的 `ingest.py`，直接进入 [§1.4](#14-启动-streamlit交互演示) 或先在终端跑 pytest / evaluate（见下表）。

---

### 1.2 可选：MongoDB + Langfuse（在 Streamlit **之前**）

需要 **Langfuse Trace**、**多轮会话 API** 或 Chat API 时，先启中间件，**再**做离线链路或打开 Streamlit：

```bash
bash scripts/setup.sh services    # Docker：MongoDB + Langfuse
bash scripts/run_api.sh           # 可选：http://127.0.0.1:8000
```

| 项 | 说明 |
|----|------|
| 是否必须 | **否**。作业五项 RAG（解析 / 问答 / 引用 / 评测）可不启 Docker |
| 与离线链路 | `evaluate.py`、Streamlit 问答可写 Langfuse；未启时设 `LANGFUSE_ENABLED=false` 或忽略 Trace 链接 |
| 文档 | [environment.md](../setup/environment.md)、[LANGFUSE.md](../integrations/LANGFUSE.md)、[chat-api.md](../integrations/chat-api.md) |

---

### 1.3 可选：离线链路（ingest → pytest → evaluate）

**目的**：在终端一次性完成 **PDF 解析 → 向量/关键词索引 → 单元测试 → 9 题自动评测**，产出 `artifacts/parsed/`、`artifacts/faiss/`、`artifacts/eval_report.json` 等，便于录屏终端段落或 CI 式验收。

**是否必须**：三步均为**可选项**，可按需跳过或改在 Streamlit 完成等价操作：

| 步骤 | 终端命令（可选） | Streamlit 等价 | 跳过条件 |
|------|------------------|----------------|----------|
| 解析 + 建库 | `scripts/ingest.py` | **入库** Tab →「完整 ingest（覆盖重建）」 | 路径 B 且仓库已有合格 `artifacts/` |
| 单元测试 | `pytest tests/ -q` | **无**（须终端） | 非提交终验时可略 |
| 构建评测 | `scripts/evaluate.py` | **构建阶段评测报告** Tab | 非提交终验时可略；终验须 `eval_overall_pass=true`（终端或 UI 任一即可） |

**推荐终端顺序**（在启动 Streamlit **之前**执行；统一 `.venv/bin/python`）：

```bash
source .venv/bin/activate

# ① 解析 + 向量/BM25 索引（可选；路径 B 可跳过）
#.venv/bin/python scripts/ingest.py
# 全量重建：
.venv/bin/python scripts/ingest.py --force-full
# 开启 INDEX_HYPOTHETICAL_QUESTIONS 时，问句生成会对每个 chunk 调 ARK，耗时可达十余分钟；
# 若出现 WARNING「Question gen failed for <chunk_id>」通常仅为该块无问句向量，ingest 会继续；
# 成功结束应看到「Ingest OK」且更新 artifacts/faiss/index_meta.json 时间戳。

# ② 单元测试（可选）
.venv/bin/python -m pytest tests/ -q

# ③ 9 题评测（可选；须索引已就绪）
.venv/bin/python scripts/evaluate.py
```

MinerU 异常时（仅 ingest 需要）：

```bash
bash scripts/fix_mineru_env.sh
.venv/bin/python scripts/mineru_ocr_weights.py
```

**入库验收**（ingest 后，终端或 Streamlit 解析预览均可对照）。建议截图 `docs/demo/screenshots/02-ingest-terminal.png`：

```bash
.venv/bin/python -c "
import json
from pathlib import Path
d = json.loads(Path('artifacts/parsed/doc.json').read_text())
q = d.get('quality', {})
print('quality.passed:', q.get('passed'))
print('table blocks:', sum(1 for b in d.get('blocks',[]) if b.get('chunk_type')=='table'))
print('has 4.1.2:', any('4.1.2' in (b.get('text') or '') for b in d.get('blocks',[])))
print('has 表1:', any(b.get('table_id')=='表1' for b in d.get('blocks',[])))
"
```

期望：`quality.passed=True`，含 **表1** 与条款 **4.1.2**；`artifacts/faiss/index_meta.json` 中 `dual_dense_enabled=true`。

**仅跑评测、不重建库**（路径 B 常见）：配置好 `.env` 后直接执行 `pytest` / `evaluate.py`，无需再跑 `ingest.py`。

作业要求 **⑤** 的指标说明、Judge 开关与报告字段见 [§5](#5-自测与评测作业要求⑤)。

---

### 1.4 启动 Streamlit（交互演示）

离线链路（或路径 B 自带 `artifacts/`）就绪后：

```bash
cd pdf-agent
bash scripts/run_streamlit.sh
```

浏览器打开 **http://localhost:8501**。

| Tab | 作用 | 与离线链路关系 |
|-----|------|----------------|
| **入库** | 触发 ingest | 等同 `scripts/ingest.py --force-full` |
| **解析预览** | 查看正文/表格/质量闸门 | 对照 [§2](#2-pdf-解析结果正文--表格) |
| **问答** | 手动五题演示 | 对照 [§3](#3-至少-5-个问答含-1-表题--1-无答案) |
| **构建阶段评测报告** | 9 题自动评测 | 等同 `scripts/evaluate.py`（`pytest` 仍须在终端） |

若 §1.3 已在终端跑过 ingest / evaluate，Streamlit 直接用于**展示与补拍截图**即可；若跳过 §1.3，可在 UI 内完成 ingest 与评测，再进入 §2～§4。

---

## 2. PDF 解析结果（正文 + 表格）

对应作业要求 **② 解析结果**。

### 方式一：Streamlit「解析预览」Tab（推荐）

建议截图 `docs/demo/screenshots/03-parse-preview.png`：

1. 打开 **解析预览**。
2. 查看顶部指标：**Chunks**、**Tables**（≥1）、**质量闸门 = 通过**。
3. 展开 **表格块预览**，确认表 1 内容（尺寸/公差/AQL 等）。
4. 阅读 **质量报告** 与块列表：筛选 `chunk_type=clause` 的正文条款（如 3.2、3.3、4.1.2）。
5. 在块列表中定位 `table_id=表1` 的表格块。

### 方式二：终端查看 `doc.json`

```bash
.venv/bin/python -c "
import json
from pathlib import Path
blocks = json.loads(Path('artifacts/parsed/doc.json').read_text())['blocks']
for b in blocks:
    if b.get('chunk_type')=='table':
        print('---', b.get('table_id'), 'page', b.get('page'))
        print((b.get('text') or '')[:500])
"

# 正文 Markdown（路径以 doc.json 的 md_ingest_dir 为准）
ls artifacts/parsed/md_ingest/mineru/
```

**说明**：全文来自 MinerU OCR + `structure.py` 分块，非手工录入；`quality.passed=false` 时 ingest 会被阻塞。目录 `artifacts/` 可能在 IDE 中默认隐藏。

---

## 3. 至少 5 个问答（含 1 表题 + 1 无答案）

对应作业要求 **③ ≥5 问**。在 Streamlit **问答** Tab 依次输入（可复制粘贴）。

| 顺序 | 题号 | 问题 | 类型 | 演示重点 |
|------|------|------|------|----------|
| 1 | q05 | 本标准对手机蓝牙配对与加密协议有何要求？ | **无答案/拒答** | 经检索+reflect 拒答（非关键词短路）；终稿为拒答模板，不编造蓝牙内容 |
| 2 | q03 | 请根据标准中的表格说明键的尺寸、公差或相关参数限值。 | **表格** | 答案含表 1 数据；引用含 `[p.N 表1]` |
| 3 | q02 | 键的技术要求中，对表面粗糙度或外观质量有哪些规定？ | 条款 | 引用 3.2/3.3；**勿在答案中展开整张表 1** |
| 4 | q06 | 这标准管啥的？键得满足啥？ | 模糊问 | 口语化问题也能答出范围与技术要求 |
| 5 | q08a | 键的检验规则包括哪些内容？ | 检验/回归 | 抽样、表 1、验收等 + 引用 |

完整 9 题定义见 [`scripts/demo_questions.json`](../../scripts/demo_questions.json)；`evaluate.py` 对全部 9 题跑分。

### 操作步骤

1. 确认页面提示「索引已就绪」。
2. 在输入框逐题发送，等待「检索 + 生成 + 反思」完成。
3. 每题展开助手消息下的 **「引用 / 自检 / 证据」**（见 [§4](#4-来源引用和自检结果)）。
4. 建议截图：
   - `04-qa-table.png` — q03
   - `05-qa-refuse.png` — q05
   - `06-qa-clause.png` — q02 或 q08a

**q02 注意**：答案聚焦外观/粗糙度条款即可，避免大段复述表 1，否则 LLM Judge 可能误杀。

作业要求 **⑤** 的 `pytest` / `evaluate.py` 属于 [§1.3 离线链路](#13-可选离线链路ingest--pytest--evaluate)，应在 Streamlit 之前于终端执行，或在 **构建阶段评测报告** Tab 完成评测；与本节手动五题相互独立。录屏可将终端评测放在 ingest 之后、问答之前，见 [demo-recording-guide.md](./demo-recording-guide.md)。

---

## 4. 来源引用和自检结果

对应作业要求 **④ 引用与自检**。

每问完成后，在回答下方展开 **「引用 / 自检 / 证据」**，JSON 重点字段：

| 字段 | 含义 | 期望（示例） |
|------|------|----------------|
| `citations` | 页码/表引用列表 | 有答案题含 `[p.N]`；表题含 `[p.N 表1]` |
| `verification.has_evidence` | 是否有检索证据 | 有答案题为 `true`；拒答题为 `false` |
| `verification.hallucination_risk` | 幻觉风险 | 低；无据时配合拒答 |
| `verification.should_refuse` | 是否应拒答 | q05 为 **`true`** |
| `reflection_notes` | LangGraph 反思记录 | 可展示重检索或修正过程 |
| `evidence` | Top 证据片段（前 5 条） | 表题应出现 `chunk_type=table` |

建议截图 `docs/demo/screenshots/07-self-check.png`（任选一题的 expander 全屏）。

若已配置 Langfuse，`extra.langfuse_trace` 可打开 Trace 对照检索/生成（见 [LANGFUSE.md](../integrations/LANGFUSE.md)）。

规范细节见 [agent-and-refusal-spec.md](../agent/agent-and-refusal-spec.md)。

---

## 5. 自测与评测（作业要求⑤）

对应作业要求 **⑤ 测试/评估**，为 [§1.3 离线链路](#13-可选离线链路ingest--pytest--evaluate) 中 **pytest**、**evaluate.py** 的展开说明。

| 项 | 说明 |
|----|------|
| 执行时机 | **ingest 之后、Streamlit 之前**（终端）；`evaluate` 也可在 Streamlit **构建阶段评测报告** Tab 完成 |
| 与 §3 关系 | 9 题自动评测与手动五题演示**相互独立**；终验须 `eval_overall_pass=true` |
| 命令入口 | 见 §1.3 推荐顺序；勿依赖系统 `python` |

```bash
source .venv/bin/activate
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/evaluate.py
```

### 5.1 单元测试（`pytest`）

覆盖解析分块、检索钉住、拒答/引用逻辑、评测指标计算等（`tests/` 目录）；**不依赖** Streamlit，一般也**不需要**重新 ingest。

| 项 | 说明 |
|----|------|
| 命令 | `.venv/bin/python -m pytest tests/ -q` |
| 期望 | 终端末尾无 FAILED；退出码 0 |
| 失败时 | 根据报错修代码或环境后重跑；未通过前勿以 `evaluate.py` 结果作为提交依据 |

### 5.2 构建阶段评测（`evaluate.py`）

对 [`scripts/demo_questions.json`](../../scripts/demo_questions.json) 中 **全部 9 题**（含 [§3](#3-至少-5-个问答含-1-表题--1-无答案) 的五题及模糊/OCR/回归等）依次走与线上一致的 RAG 链路，写入 `artifacts/eval_report.json`。

| 项 | 说明 |
|----|------|
| 命令 | `.venv/bin/python scripts/evaluate.py` |
| 前置 | 已 `ingest`；`artifacts/faiss/` 与 `artifacts/parsed/doc.json` 存在 |
| 终端验收 | 最后一行 **`eval_overall_pass=True`**（注意大小写以脚本输出为准） |
| 文件验收 | `artifacts/eval_report.json` 内 `"eval_overall_pass": true`（`EVAL_PASS_STRICT=true` 为默认严格模式） |
| 退出码 | 0 = 通过；1 = 未通过 |

快速查看报告摘要（可选）：

```bash
.venv/bin/python -c "
import json
from pathlib import Path
r = json.loads(Path('artifacts/eval_report.json').read_text())
m = r.get('metrics', r)
print('eval_overall_pass:', r.get('eval_overall_pass'))
print('llm_judge_pass_rate:', m.get('llm_judge_pass_rate'))
print('refuse_accuracy:', m.get('refuse_accuracy'))
"
```

**开发期**可跳过 LLM Judge，仅检查检索与规则指标（**终验/提交勿用**）：

```bash
.venv/bin/python scripts/evaluate.py --skip-llm-judge
```

**Streamlit 等价**：在 **构建阶段评测报告** Tab 运行评测，逻辑与 `evaluate.py` 一致；若 §1.3 已在终端跑过，此处用于对照或补截图即可。

建议截图 `docs/demo/screenshots/08-evaluate.png`（终端 `eval_overall_pass=true` 或评测 Tab 全屏）。

### 5.3 导出文字版证明（可选提交）

```bash
.venv/bin/python scripts/export_eval_proof.py
# 生成 docs/demo/eval-proof.md（须先 eval_overall_pass=true）
```

### 5.4 主要硬性指标（摘要）

`eval_overall_pass=true` 表示下表及相关项（含 fuzzy / ocr / regression）在严格模式下全部达标；完整定义见 [evaluation-spec.md](./evaluation-spec.md)、[submission-checklist.md](./submission-checklist.md)。

| 指标 | 阈值 |
|------|------|
| refuse_accuracy | 1.0 |
| false_refuse_rate | 0 |
| citation_compliance | 1.0 |
| table_retrieval_hit | 1.0（有表题时） |
| clause_retrieval_hit | ≥ 0.8（有条款题时） |
| reflection_fields_present | 1.0 |
| unsupported_claims_empty | 1.0 |
| llm_judge_pass_rate | ≥ 0.8 |
| fuzzy / ocr / regression | 通过 |

`llm_judge_pass_rate` 因 Judge 非确定性可能边界波动；**优先重跑** `evaluate.py`，并检查 q02 是否在答案中误展开整张表 1。

---

## 6. 五项要求 ↔ 证据对照

| 作业要求 | 操作位置 | 建议证据 |
|----------|----------|----------|
| ① 部署/启动 | `setup.sh` → `check_env.sh` →（可选）`services` →（可选）[§1.3](#13-可选离线链路ingest--pytest--evaluate) → `run_streamlit.sh` | `01-setup.png`、`02-ingest-terminal.png` |
| ② 解析正文+表 | §1.3 ingest 和/或 **解析预览** Tab / `doc.json` | `03-parse-preview.png` |
| ③ ≥5 问（表+无答案） | **问答** Tab 五题（上表） | `04`～`06` |
| ④ 引用+自检 | 每题「引用 / 自检 / 证据」 | `07-self-check.png` |
| ⑤ 测试/评估 | §1.3：`pytest` → `evaluate.py`（**ingest 后、Streamlit 前**）；或 **评测报告** Tab | `08-evaluate.png` |

截图命名清单：[demo/screenshots/README.md](../demo/screenshots/README.md)。录屏分镜：[demo-recording-guide.md](./demo-recording-guide.md)。

---

## 7. 执行 Checklist

```text
[ ] §1.1：setup.sh + .env + check_env.sh（all 或 minimal）
[ ] §1.2（可选）：setup.sh services；需要会话/API 时再 run_api.sh
[ ] §1.3（可选）：ingest → pytest -q → evaluate.py（或改在 Streamlit 入库/评测 Tab）
[ ] §1.3 验收：quality.passed=true、含表1；eval_overall_pass=true（终验）
[ ] §1.4：run_streamlit.sh → 解析预览截图（§2）
[ ] 问答 Tab：q05 → q03 → q02 → q06 → q08a（各展开引用/自检，§3～§4）
[ ] （可选）export_eval_proof.py；打包 docs/demo/screenshots/
```

---

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| `magic-pdf` 不可用 | `bash scripts/setup.sh` 后重启 Streamlit |
| `quality.passed=false` | 解析预览看质量报告 → `ingest.py --force-full` |
| `eval_overall_pass=false` 且 Judge 未达标 | 重跑 `evaluate.py`；检查 q02 是否误展开整表 |
| 索引未就绪 | 先 ingest，或 `minimal` 路径确认 `artifacts/faiss/` |
| Docker 未启 | RAG 五项演示可忽略；需要 Langfuse/会话时在 **Streamlit 前** `bash scripts/setup.sh services` |

更全排障：[environment.md](../setup/environment.md) 第 5 节。

---

## 修订

| 日期 | 说明 |
|------|------|
| 2026-05-27 | 初版：对齐作业五项要求与 submission-checklist 五题 |
| 2026-05-27 | 补全 §5 自测/评测流程；路径 A/B 与 §3 串联 pytest、evaluate.py |
| 2026-05-27 | 重组 §1：ingest/pytest/evaluate 置于 Streamlit 前；明确可选项与 UI 等价；Langfuse 提前 |
