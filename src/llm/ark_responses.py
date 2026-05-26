from __future__ import annotations

import logging
import time
from typing import Any

from openai import OpenAI

from src.config.settings import Settings, get_settings
from src.observability.usage import log_usage

logger = logging.getLogger(__name__)


def _usage_tokens(usage: Any) -> tuple[int, int, int]:
    if usage is None:
        return 0, 0, 0
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", inp + out) or (inp + out))
    return inp, out, total


def ark_responses_create(
    *,
    input_payload: list[dict[str, Any]],
    model: str | None = None,
    temperature: float = 0.0,
    settings: Settings | None = None,
    stage: str = "ark_responses",
    session_id: str | None = None,
) -> str:
    """
    调用火山方舟 Responses API（POST /api/v3/responses）。

    多模态内容使用 input_image + input_text，与官方 curl 示例一致。
    """
    cfg = settings or get_settings()
    if not cfg.ark_api_key:
        raise ValueError("ARK_API_KEY is required")

    client = OpenAI(api_key=cfg.ark_api_key, base_url=cfg.ark_base_url)
    model_id = model or cfg.ark_vl_model

    t0 = time.perf_counter()
    resp = client.responses.create(
        model=model_id,
        input=input_payload,
        temperature=temperature,
    )
    latency = int((time.perf_counter() - t0) * 1000)

    inp, out, total = _usage_tokens(resp.usage)
    log_usage(
        stage=stage,
        model=model_id,
        prompt_tokens=inp,
        completion_tokens=out,
        total_tokens=total,
        latency_ms=latency,
        session_id=session_id,
    )

    text = (resp.output_text or "").strip()
    if not text:
        logger.warning("ARK responses returned empty output_text (model=%s)", model_id)
    return text
