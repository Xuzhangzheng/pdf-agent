from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx
from openai import OpenAI

from src.config.settings import Settings, get_settings
from src.observability.usage import log_usage

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    index: int
    relevance_score: float


class Reranker:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._degraded: str | bool = False

    @property
    def degraded(self) -> str | bool:
        return self._degraded

    def _dashscope_rerank_url(self) -> str:
        """Rerank 走 compatible-api，勿与 Embedding 的 compatible-mode 混用。"""
        base = (self.settings.dashscope_rerank_base_url or "").strip()
        if not base:
            base = self.settings.dashscope_base_url.replace(
                "compatible-mode", "compatible-api"
            )
        return base.rstrip("/") + "/reranks"

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        *,
        question_id: str | None = None,
        retrieval_round: int = 0,
        session_id: str | None = None,
    ) -> list[RerankResult]:
        top_n = top_n or self.settings.rerank_top_n
        if not documents:
            return []

        backend = self.settings.reranker_backend.lower()
        if backend == "dashscope":
            try:
                return self._rerank_dashscope(
                    query,
                    documents,
                    top_n,
                    question_id=question_id,
                    retrieval_round=retrieval_round,
                    session_id=session_id,
                )
            except Exception as e:
                logger.warning("DashScope rerank failed: %s", e)
                try:
                    return self._rerank_local(
                        query,
                        documents,
                        top_n,
                        session_id=session_id,
                        retrieval_round=retrieval_round,
                        question_id=question_id,
                    )
                except Exception as e2:
                    logger.warning("Local BGE rerank failed: %s", e2)

        elif backend == "local_bge":
            try:
                return self._rerank_local(
                    query,
                    documents,
                    top_n,
                    session_id=session_id,
                    retrieval_round=retrieval_round,
                    question_id=question_id,
                )
            except Exception as e:
                logger.warning("Local BGE rerank failed: %s", e)

        self._degraded = True
        return [
            RerankResult(index=i, relevance_score=1.0 - i * 0.01)
            for i in range(min(top_n, len(documents)))
        ]

    def _rerank_dashscope(
        self,
        query: str,
        documents: list[str],
        top_n: int,
        *,
        question_id: str | None,
        retrieval_round: int,
        session_id: str | None,
    ) -> list[RerankResult]:
        if not self.settings.dashscope_api_key:
            raise ValueError("DASHSCOPE_API_KEY required for rerank")

        url = self._dashscope_rerank_url()
        payload = {
            "model": self.settings.reranker_model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
            "instruct": self.settings.reranker_instruct,
        }
        t0 = time.perf_counter()
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.settings.dashscope_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        latency = int((time.perf_counter() - t0) * 1000)
        usage = data.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)
        results = data.get("results", [])
        out = [
            RerankResult(index=int(r["index"]), relevance_score=float(r["relevance_score"]))
            for r in results
        ]
        log_usage(
            stage="retrieve_rerank_dashscope",
            model=self.settings.reranker_model,
            total_tokens=total_tokens,
            latency_ms=latency,
            question_id=question_id,
            retrieval_round=retrieval_round,
            session_id=session_id,
            input={
                "query": query,
                "document_count": len(documents),
                "document_previews": [d[:300] for d in documents[:3]],
                "top_n": top_n,
            },
            output={
                "results": [
                    {"index": r.index, "relevance_score": r.relevance_score} for r in out
                ],
            },
        )
        self._degraded = False
        return out[:top_n]

    def _rerank_local(
        self,
        query: str,
        documents: list[str],
        top_n: int,
        *,
        session_id: str | None,
        retrieval_round: int,
        question_id: str | None,
    ) -> list[RerankResult]:
        from sentence_transformers import CrossEncoder

        t0 = time.perf_counter()
        model = CrossEncoder(self.settings.reranker_local_model)
        pairs = [[query, d] for d in documents]
        scores = model.predict(pairs)
        latency = int((time.perf_counter() - t0) * 1000)
        ranked = sorted(
            [
                RerankResult(index=i, relevance_score=float(scores[i]))
                for i in range(len(documents))
            ],
            key=lambda x: x.relevance_score,
            reverse=True,
        )
        top = ranked[:top_n]
        log_usage(
            stage="retrieve_rerank_local",
            model=self.settings.reranker_local_model,
            latency_ms=latency,
            question_id=question_id,
            retrieval_round=retrieval_round,
            session_id=session_id,
            input={
                "query": query,
                "document_count": len(documents),
                "document_previews": [d[:300] for d in documents[:3]],
                "top_n": top_n,
            },
            output={
                "results": [
                    {"index": r.index, "relevance_score": r.relevance_score} for r in top
                ],
            },
        )
        self._degraded = "local_fallback"
        return ranked[:top_n]
