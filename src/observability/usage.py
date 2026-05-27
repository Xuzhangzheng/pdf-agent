"""Token 与成本记录：统一导出至 Langfuse（已弃用 JSONL 文件）。"""
from __future__ import annotations

from typing import Any

from src.observability.langfuse_telemetry import (
    flush_langfuse,
    record_generation,
    summarize_sessions,
)


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
    input: Any | None = None,
    output: Any | None = None,
) -> None:
    record_generation(
        stage=stage,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        question_id=question_id,
        retrieval_round=retrieval_round,
        session_id=session_id,
        extra=extra,
        input=input,
        output=output,
    )


def summarize_usage(session_ids: list[str] | None = None) -> dict[str, Any]:
    return summarize_sessions(session_ids)


__all__ = ["log_usage", "summarize_usage", "flush_langfuse"]
