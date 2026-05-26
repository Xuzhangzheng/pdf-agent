from __future__ import annotations

import logging
import time

from openai import OpenAI

from src.config.settings import Settings, get_settings
from src.observability.usage import log_usage

logger = logging.getLogger(__name__)


class DashScopeEmbedder:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client = OpenAI(
            api_key=self.settings.dashscope_api_key,
            base_url=self.settings.dashscope_base_url,
        )

    def embed_texts(self, texts: list[str], session_id: str | None = None) -> list[list[float]]:
        if not self.settings.dashscope_api_key:
            raise ValueError("DASHSCOPE_API_KEY is required for embedding")

        batch_size = self.settings.embedding_batch_size
        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            t0 = time.perf_counter()
            resp = self.client.embeddings.create(
                model=self.settings.embedding_model,
                input=batch,
                dimensions=self.settings.embedding_dimensions,
            )
            latency = int((time.perf_counter() - t0) * 1000)
            usage = getattr(resp, "usage", None)
            total_tokens = getattr(usage, "total_tokens", 0) if usage else 0
            log_usage(
                stage="embed",
                model=self.settings.embedding_model,
                prompt_tokens=total_tokens,
                completion_tokens=0,
                total_tokens=total_tokens,
                latency_ms=latency,
                session_id=session_id,
            )
            ordered = sorted(resp.data, key=lambda d: d.index)
            all_vectors.extend([d.embedding for d in ordered])
        return all_vectors
