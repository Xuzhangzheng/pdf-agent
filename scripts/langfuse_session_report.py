#!/usr/bin/env python3
"""从 Langfuse 拉取单次/最近问答 Trace，生成 Markdown 流程与 Token 报告。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from src.config.settings import get_settings
from src.observability.langfuse_telemetry import langfuse_enabled, summarize_sessions


def _auth() -> tuple[str, str]:
    s = get_settings()
    return (s.langfuse_public_key, s.langfuse_secret_key)


def _base() -> str:
    return get_settings().langfuse_host.rstrip("/")


def fetch_traces(*, limit: int = 10, session_id: str | None = None) -> list[dict]:
    url = f"{_base()}/api/public/traces"
    params: dict = {"limit": limit}
    if session_id:
        params["sessionId"] = session_id
    with httpx.Client(timeout=60.0) as http:
        r = http.get(url, params=params, auth=_auth())
        r.raise_for_status()
        data = r.json()
    if isinstance(data, dict) and "data" in data:
        return list(data["data"])
    return list(data) if isinstance(data, list) else []


def fetch_observations(trace_id: str) -> list[dict]:
    url = f"{_base()}/api/public/observations"
    params = {"traceId": trace_id, "limit": 100}
    with httpx.Client(timeout=60.0) as http:
        r = http.get(url, params=params, auth=_auth())
        r.raise_for_status()
        data = r.json()
    if isinstance(data, dict) and "data" in data:
        return list(data["data"])
    return list(data) if isinstance(data, list) else []


def _usage_tokens(obs: dict) -> int:
    usage = obs.get("usage") or obs.get("usageDetails") or {}
    if not isinstance(usage, dict):
        return 0
    t = usage.get("totalTokens") or usage.get("total_tokens") or 0
    if t:
        return int(t)
    inp = int(usage.get("input") or usage.get("prompt_tokens") or 0)
    out = int(usage.get("output") or usage.get("completion_tokens") or 0)
    return inp + out


def _obs_sort_key(obs: dict) -> str:
    return str(obs.get("startTime") or obs.get("createdAt") or "")


def build_markdown_report(trace: dict, observations: list[dict]) -> str:
    trace_id = trace.get("id") or trace.get("traceId") or "—"
    name = trace.get("name") or "—"
    session = trace.get("sessionId") or trace.get("session_id") or "—"
    latency = trace.get("latency") or trace.get("duration") or "—"

    lines = [
        f"# Langfuse 问答流程报告",
        "",
        f"- **生成时间**: {datetime.now(timezone.utc).isoformat()}",
        f"- **trace_id**: `{trace_id}`",
        f"- **session_id**: `{session}`",
        f"- **问题（trace 名）**: {name}",
        f"- **总延迟**: {latency}",
        f"- **Langfuse UI**: {_base()}/trace/{trace_id}",
        "",
        "## 执行路径（按时间）",
        "",
        "| 顺序 | 类型 | 名称 | Token | 延迟(ms) |",
        "|------|------|------|-------|----------|",
    ]

    sorted_obs = sorted(observations, key=_obs_sort_key)
    total_tokens = 0
    for i, obs in enumerate(sorted_obs, 1):
        otype = obs.get("type") or "—"
        oname = obs.get("name") or "—"
        tok = _usage_tokens(obs)
        total_tokens += tok
        lat = obs.get("latency") or obs.get("completionStartTime") or "—"
        if isinstance(lat, (int, float)):
            lat_ms = int(lat)
        else:
            lat_ms = "—"
        lines.append(f"| {i} | {otype} | {oname} | {tok} | {lat_ms} |")

    lines.extend(
        [
            "",
            f"**观测步数合计 Token（近似）**: {total_tokens}",
            "",
            "## 节点详情",
            "",
        ]
    )

    for obs in sorted_obs:
        oname = obs.get("name") or "observation"
        lines.append(f"### {oname}")
        lines.append("")
        if obs.get("input"):
            inp = obs["input"]
            if isinstance(inp, (dict, list)):
                inp = json.dumps(inp, ensure_ascii=False)[:2000]
            else:
                inp = str(inp)[:2000]
            lines.append(f"**Input（摘要）**: {inp}")
            lines.append("")
        if obs.get("output"):
            out = obs["output"]
            if isinstance(out, (dict, list)):
                out = json.dumps(out, ensure_ascii=False)[:2000]
            else:
                out = str(out)[:2000]
            lines.append(f"**Output（摘要）**: {out}")
            lines.append("")
        meta = obs.get("metadata")
        if meta:
            lines.append(f"**Metadata**: `{json.dumps(meta, ensure_ascii=False)[:500]}`")
            lines.append("")

    cost = summarize_sessions([session] if session != "—" else [trace_id])
    lines.extend(
        [
            "## Token 汇总（API 聚合）",
            "",
            "```json",
            json.dumps(cost, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Langfuse 单次/最近问答 Markdown 报告")
    parser.add_argument("--session-id", help="trace_id / session_id（与 ask() 返回一致）")
    parser.add_argument("--latest", type=int, default=0, help="取最近 N 条 trace 中的第一条")
    parser.add_argument(
        "-o",
        "--output",
        default="artifacts/langfuse_session_report.md",
        help="输出 Markdown 路径",
    )
    args = parser.parse_args()

    if not langfuse_enabled():
        print("Langfuse 未启用：请配置 LANGFUSE_HOST / PUBLIC_KEY / SECRET_KEY", file=sys.stderr)
        return 1

    traces: list[dict] = []
    if args.session_id:
        traces = fetch_traces(limit=5, session_id=args.session_id)
        if not traces:
            one = fetch_traces(limit=1)
            traces = [t for t in one if (t.get("id") or t.get("traceId")) == args.session_id]
        if not traces:
            try:
                url = f"{_base()}/api/public/traces/{args.session_id}"
                with httpx.Client(timeout=60.0) as http:
                    r = http.get(url, auth=_auth())
                    if r.status_code == 200:
                        traces = [r.json()]
            except Exception:
                pass
    elif args.latest > 0:
        traces = fetch_traces(limit=args.latest)
    else:
        parser.error("请指定 --session-id 或 --latest N")

    if not traces:
        print("未找到 Trace，请先在 Streamlit/ask 提问并 flush。", file=sys.stderr)
        return 1

    trace = traces[0]
    trace_id = trace.get("id") or trace.get("traceId")
    observations = fetch_observations(trace_id)
    report = build_markdown_report(trace, observations)

    out = get_settings().resolve_path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"Wrote {out}")
    print(f"UI: {_base()}/trace/{trace_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
