"""Langfuse 统一遥测：替代 artifacts/usage/*.jsonl。"""
from __future__ import annotations

import hashlib
import logging
import re
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Generator

import httpx

from src.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_LANGFUSE_CLIENT: Any | None = None
_CLIENT_CHECKED = False


_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def _langfuse_trace_id(session_id: str) -> str:
    """Langfuse SDK 要求 trace_id 为 32 位小写 hex；评测 sid 等非 hex 时做确定性哈希。"""
    compact = session_id.replace("-", "").lower()
    if _HEX32.fullmatch(compact):
        return compact
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]


def langfuse_enabled(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    if not s.langfuse_enabled:
        return False
    return bool(s.langfuse_public_key and s.langfuse_secret_key and s.langfuse_host)


def _io_max_chars(settings: Settings | None = None) -> int:
    s = settings or get_settings()
    return max(256, int(s.langfuse_io_max_chars))


def prepare_langfuse_io(
    value: Any,
    *,
    settings: Settings | None = None,
) -> Any | None:
    """按配置截断并脱敏后写入 Langfuse input/output；关闭 log_io 时返回 None。"""
    s = settings or get_settings()
    if not s.langfuse_log_io or value is None:
        return None
    return _truncate_value(_sanitize_io(value), max_chars=_io_max_chars(s))


def _sanitize_io(value: Any) -> Any:
    """脱敏多模态等大字段，避免把整段 base64 打进 Langfuse。"""
    if isinstance(value, list):
        return [_sanitize_io(item) for item in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in ("image_url", "url") and isinstance(item, str) and len(item) > 120:
                out[key] = f"<omitted {len(item)} chars>"
                continue
            if key == "data" and isinstance(item, str) and len(item) > 120:
                out[key] = f"<omitted {len(item)} chars>"
                continue
            out[key] = _sanitize_io(item)
        if value.get("type") in ("input_image", "image"):
            out.setdefault("type", value.get("type"))
            if "image_url" not in out and "url" in value:
                out["image_url"] = "<omitted>"
        return out
    return value


def _truncate_value(value: Any, *, max_chars: int) -> Any:
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return value[:max_chars] + f"… [truncated, {len(value)} chars total]"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_truncate_value(item, max_chars=max_chars) for item in value[:50]]
    if isinstance(value, dict):
        return {
            k: _truncate_value(v, max_chars=max_chars)
            for k, v in list(value.items())[:40]
        }
    text = str(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"… [truncated, {len(text)} chars total]"


@lru_cache
def _get_client_cached(
    enabled: bool,
    public_key: str,
    secret_key: str,
    host: str,
) -> Any | None:
    if not enabled:
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host.rstrip("/"),
        )
    except Exception as e:
        logger.warning("Langfuse client init failed: %s", e)
        return None


def get_langfuse_client(settings: Settings | None = None) -> Any | None:
    global _LANGFUSE_CLIENT, _CLIENT_CHECKED
    s = settings or get_settings()
    if _CLIENT_CHECKED and _LANGFUSE_CLIENT is None and not langfuse_enabled(s):
        return None
    client = _get_client_cached(
        langfuse_enabled(s),
        s.langfuse_public_key,
        s.langfuse_secret_key,
        s.langfuse_host,
    )
    _LANGFUSE_CLIENT = client
    _CLIENT_CHECKED = True
    return client


def flush_langfuse() -> None:
    client = get_langfuse_client()
    if client is not None:
        try:
            client.flush()
        except Exception as e:
            logger.debug("Langfuse flush: %s", e)


def _metadata_for_propagation(metadata: dict[str, Any]) -> dict[str, str]:
    """Langfuse 4 propagate_attributes 要求值为 US-ASCII 字符串且 ≤200 字符。"""
    out: dict[str, str] = {}
    for key, value in metadata.items():
        text = str(value)
        if len(text) > 200:
            text = text[:200] + "…"
        out[str(key)[:200]] = text
    return out


@contextmanager
def _start_root_span(
    client: Any,
    *,
    name: str,
    trace_context: dict[str, str],
    input: Any,
):
    """兼容 Langfuse 3.x (start_as_current_span) 与 4.x (start_as_current_observation)。"""
    if hasattr(client, "start_as_current_span"):
        with client.start_as_current_span(
            name=name,
            trace_context=trace_context,
            input=input,
        ) as span:
            yield span
        return
    with client.start_as_current_observation(
        name=name,
        as_type="span",
        trace_context=trace_context,
        input=input,
    ) as span:
        yield span


@contextmanager
def _start_generation(
    client: Any,
    *,
    name: str,
    model: str,
    metadata: dict[str, Any],
    input: Any,
):
    if hasattr(client, "start_as_current_generation"):
        with client.start_as_current_generation(
            name=name,
            model=model,
            metadata=metadata,
            input=input,
        ) as generation:
            yield generation
        return
    with client.start_as_current_observation(
        name=name,
        as_type="generation",
        model=model,
        metadata=metadata,
        input=input,
    ) as generation:
        yield generation


@contextmanager
def _trace_attributes_context(
    client: Any,
    *,
    question: str,
    session_id: str,
    trace_id: str,
    trace_input: Any,
    metadata: dict[str, Any],
) -> Generator[None, None, None]:
    trace_name = (question[:120] + "…") if len(question) > 120 else question
    full_meta = {**metadata, "trace_id_hex": trace_id, "session_id_raw": session_id}
    if hasattr(client, "update_current_trace"):
        client.update_current_trace(
            name=trace_name,
            session_id=session_id,
            input=trace_input,
            metadata=full_meta,
        )
        yield
        return
    if hasattr(client, "propagate_attributes"):
        with client.propagate_attributes(
            session_id=session_id[:200],
            trace_name=trace_name,
            metadata=_metadata_for_propagation(full_meta),
        ):
            yield
        return
    yield


@contextmanager
def query_trace_context(
    *,
    session_id: str,
    question: str,
    question_id: str | None = None,
) -> Generator[None, None, None]:
    """单次 ask/evaluate 问题的根 Trace（trace_id = session_id）。"""
    s = get_settings()
    client = get_langfuse_client(s)
    if client is None:
        yield
        return

    metadata: dict[str, Any] = {"app": "pdf-agent"}
    if question_id:
        metadata["question_id"] = question_id

    trace_id = _langfuse_trace_id(session_id)
    trace_input = prepare_langfuse_io({"question": question}, settings=s)
    try:
        with _start_root_span(
            client,
            name="pdf-agent-ask",
            trace_context={"trace_id": trace_id},
            input=trace_input,
        ):
            with _trace_attributes_context(
                client,
                question=question,
                session_id=session_id,
                trace_id=trace_id,
                trace_input=trace_input,
                metadata=metadata,
            ):
                yield
    finally:
        flush_langfuse()


@contextmanager
def span_context(
    name: str,
    *,
    metadata: dict[str, Any] | None = None,
    input: Any | None = None,
    output: Any | None = None,
) -> Generator[Any, None, None]:
    s = get_settings()
    client = get_langfuse_client(s)
    if client is None:
        yield None
        return
    span_input = prepare_langfuse_io(input, settings=s)
    span_output = prepare_langfuse_io(output, settings=s)
    try:
        if hasattr(client, "start_as_current_span"):
            cm = client.start_as_current_span(
                name=name,
                metadata=metadata or {},
                input=span_input,
            )
        else:
            cm = client.start_as_current_observation(
                name=name,
                as_type="span",
                metadata=metadata or {},
                input=span_input,
            )
        with cm as span:
            yield span
            if span_output is not None:
                span.update(output=span_output)
    except Exception as e:
        logger.debug("Langfuse span %s skipped: %s", name, e)
        yield None


def record_generation(
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
    """记录 LLM / Embedding / Rerank 调用（Generation 观测）。"""
    s = get_settings()
    client = get_langfuse_client(s)
    if client is None:
        return

    total = int(
        total_tokens
        if total_tokens is not None
        else prompt_tokens + completion_tokens
    )
    meta: dict[str, Any] = {
        "stage": stage,
        "latency_ms": latency_ms,
        "retrieval_round": retrieval_round,
    }
    if question_id:
        meta["question_id"] = question_id
    if session_id:
        meta["session_id"] = session_id
    if extra:
        meta.update(extra)

    usage_details = {
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "total_tokens": total,
    }

    gen_input = prepare_langfuse_io(input, settings=s)
    gen_output = prepare_langfuse_io(output, settings=s)

    try:
        with _start_generation(
            client,
            name=stage,
            model=model,
            metadata=meta,
            input=gen_input,
        ) as generation:
            generation.update(
                usage_details=usage_details,
                metadata=meta,
                input=gen_input,
                output=gen_output,
            )
    except Exception as e:
        logger.debug("Langfuse generation %s: %s", stage, e)


def _auth(settings: Settings) -> tuple[str, str]:
    return (settings.langfuse_public_key, settings.langfuse_secret_key)


def _fetch_trace_observations(
    trace_id: str, settings: Settings
) -> list[dict[str, Any]]:
    base = settings.langfuse_host.rstrip("/")
    url = f"{base}/api/public/observations"
    params = {"traceId": trace_id, "limit": 100}
    try:
        with httpx.Client(timeout=30.0) as http:
            r = http.get(url, params=params, auth=_auth(settings))
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("Langfuse observations fetch %s: %s", trace_id, e)
        return []
    if isinstance(data, dict) and "data" in data:
        return list(data["data"])
    if isinstance(data, list):
        return data
    return []


def summarize_sessions(
    session_ids: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """按 session_id（= trace_id）从 Langfuse 聚合 Token。"""
    s = settings or get_settings()
    if not langfuse_enabled(s):
        return {
            "total_tokens": 0,
            "by_stage": {},
            "by_model": {},
            "estimated_cost_cny": None,
            "backend": "disabled",
            "langfuse_host": s.langfuse_host,
        }

    ids = session_ids or []
    total = 0
    by_stage: dict[str, int] = {}
    by_model: dict[str, int] = {}

    for sid in ids:
        trace_id = _langfuse_trace_id(sid)
        for obs in _fetch_trace_observations(trace_id, s):
            usage = obs.get("usage") or obs.get("usageDetails") or {}
            if not isinstance(usage, dict):
                continue
            t = int(usage.get("totalTokens") or usage.get("total_tokens") or 0)
            if t <= 0:
                inp = int(usage.get("input") or usage.get("prompt_tokens") or 0)
                out = int(usage.get("output") or usage.get("completion_tokens") or 0)
                t = inp + out
            total += t
            name = str(obs.get("name") or obs.get("type") or "unknown")
            by_stage[name] = by_stage.get(name, 0) + t
            model = str(obs.get("model") or "unknown")
            by_model[model] = by_model.get(model, 0) + t

    return {
        "total_tokens": total,
        "by_stage": by_stage,
        "by_model": by_model,
        "estimated_cost_cny": None,
        "backend": "langfuse",
        "langfuse_host": s.langfuse_host,
        "trace_ids": ids,
    }
