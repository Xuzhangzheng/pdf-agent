#!/usr/bin/env python3
"""Export a markdown eval proof from artifacts/eval_report.json (for submission docs)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "eval_report.json"
OUT = ROOT / "docs" / "demo" / "eval-proof.md"


def main() -> int:
    if not REPORT.exists():
        print(f"Missing {REPORT}; run: .venv/bin/python scripts/evaluate.py", file=sys.stderr)
        return 1

    data = json.loads(REPORT.read_text(encoding="utf-8"))
    metrics = data.get("metrics", {})
    overall = data.get("eval_overall_pass", metrics.get("eval_overall_pass"))
    run_at = data.get("run_at", "—")
    run_id = data.get("run_id", "—")

    status_note = (
        "**当前快照未达提交线**（`eval_overall_pass=false`）。"
        " 常见原因：`llm_judge_pass_rate` < 0.8（Judge 非确定性）。"
        " 提交前请重跑 `evaluate.py` 直至通过，再执行本脚本并截取终端 `eval_overall_pass=true`。"
        if not overall
        else "**当前快照已达提交线。** 请保留终端截图作为 §四-3 评测证据。"
    )

    lines = [
        "# 评测验收证明（自动生成）",
        "",
        "> 由 `scripts/export_eval_proof.py` 从 `artifacts/eval_report.json` 生成。",
        "> **勿**将 API Key 写入本文件。截图演示请对终端 `eval_overall_pass=true` 画面拍照。",
        "",
        status_note,
        "",
        f"- **run_at**: {run_at}",
        f"- **run_id**: {run_id}",
        f"- **eval_overall_pass**: `{overall}`",
        "",
        "## 全局指标",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
    ]
    for k, v in sorted(metrics.items()):
        if k == "eval_overall_pass":
            continue
        lines.append(f"| `{k}` | {v} |")

    lines.extend(["", "## 逐题摘要", "", "| id | judge_pass | should_refuse | citations |", "|----|------------|-----------------|-----------|"])
    for row in data.get("per_question_results", []):
        vid = row.get("id", "")
        judge = row.get("llm_judge_pass", "—")
        ver = row.get("verification") or {}
        refuse = ver.get("should_refuse", "—")
        cites = row.get("citation_count", "—")
        lines.append(f"| {vid} | {judge} | {refuse} | {cites} |")

    lines.extend(
        [
            "",
            "## 复现命令",
            "",
            "```bash",
            "source .venv/bin/activate",
            ".venv/bin/python -m pytest tests/ -q",
            ".venv/bin/python scripts/evaluate.py",
            ".venv/bin/python scripts/export_eval_proof.py",
            "```",
            "",
            "作业硬性要求：`eval_overall_pass=true`（含 `llm_judge_pass_rate` ≥ 0.8）。未通过时可重跑 evaluate。",
            "",
        ]
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"eval_overall_pass={overall}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
