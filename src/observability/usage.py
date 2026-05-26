from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.settings import get_settings


def _usage_path(session_id: str) -> Path:
    settings = get_settings()
    base = settings.resolve_path(settings.usage_log_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{session_id}.jsonl"


def log_usage(
    *,
    stage: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int | None = None,
    latency_ms: int = 0,
    question_id: str | None = None,
    retrieval_round: int = 0,
    session_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    settings = get_settings()
    if not settings.log_token_usage:
        return
    sid = session_id or str(uuid.uuid4())
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens if total_tokens is not None else prompt_tokens + completion_tokens,
        "latency_ms": latency_ms,
        "question_id": question_id,
        "retrieval_round": retrieval_round,
        "session_id": sid,
    }
    if extra:
        row.update(extra)
    path = _usage_path(sid)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize_usage(session_ids: list[str] | None = None) -> dict[str, Any]:
    settings = get_settings()
    base = settings.resolve_path(settings.usage_log_dir)
    if not base.exists():
        return {"total_tokens": 0, "by_stage": {}, "by_model": {}}

    files = list(base.glob("*.jsonl"))
    if session_ids:
        files = [base / f"{sid}.jsonl" for sid in session_ids if (base / f"{sid}.jsonl").exists()]

    total = 0
    by_stage: dict[str, int] = {}
    by_model: dict[str, int] = {}
    for fp in files:
        for line in fp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            t = int(row.get("total_tokens", 0))
            total += t
            st = row.get("stage", "unknown")
            by_stage[st] = by_stage.get(st, 0) + t
            m = row.get("model", "unknown")
            by_model[m] = by_model.get(m, 0) + t
    return {
        "total_tokens": total,
        "by_stage": by_stage,
        "by_model": by_model,
        "estimated_cost_cny": None,
    }
