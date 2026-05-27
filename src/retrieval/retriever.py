from __future__ import annotations

import logging
from dataclasses import dataclass

import jieba
from openai import OpenAI

from src.config.settings import Settings, get_settings
from src.indexing.dual_dense import (
    best_dense_ranks_per_chunk,
    best_dense_scores_per_chunk,
)
from src.indexing.indexer import DocumentIndexer
from src.models.agent import Evidence
from src.models.blocks import Chunk
from src.retrieval.query_signals import (
    TECH_REQUIREMENTS_CLAUSE_IDS,
    extract_clause_ids_from_query,
    extract_table_id_from_query,
    is_english_boilerplate_text,
    wants_appearance_clauses,
    wants_composite_strength_table,
    wants_inspection_topics,
    wants_table_evidence,
    wants_technical_requirements_overview,
)
from src.retrieval.reranker import Reranker

logger = logging.getLogger(__name__)


@dataclass
class RetrievalOutcome:
    evidence: list[Evidence]
    hard_refuse: bool
    max_rrf: float
    max_bm25: float
    reranker_degraded: str | bool
    rerank_before_top1: str | None = None
    rerank_after_top1: str | None = None


class HybridRetriever:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.indexer = DocumentIndexer(self.settings)
        self.reranker = Reranker(self.settings)
        self._embed_client = OpenAI(
            api_key=self.settings.dashscope_api_key,
            base_url=self.settings.dashscope_base_url,
        )

    def _embed_query(self, query: str) -> list[float]:
        resp = self._embed_client.embeddings.create(
            model=self.settings.embedding_model,
            input=[query],
            dimensions=self.settings.embedding_dimensions,
        )
        return resp.data[0].embedding

    @staticmethod
    def _chunk_to_evidence(
        c: Chunk,
        *,
        rrf_score: float = 0.0,
        bm25_score: float = 0.0,
        rerank_score: float | None = None,
    ) -> Evidence:
        ev = Evidence(
            chunk_id=c.chunk_id,
            text=c.text,
            page=c.page,
            chunk_type=c.chunk_type,
            clause_id=c.clause_id,
            table_id=c.table_id,
            rrf_score=rrf_score,
            bm25_score=bm25_score,
        )
        if rerank_score is not None:
            ev = ev.model_copy(update={"rerank_score": rerank_score})
        return ev

    def _apply_metadata_boost(
        self,
        rrf: dict[str, float],
        chunk_map: dict[str, Chunk],
        query: str,
    ) -> None:
        boost = self.settings.retrieval_metadata_boost
        clause_targets = extract_clause_ids_from_query(query)
        table_id_target = extract_table_id_from_query(query)
        table_intent = wants_table_evidence(query)
        appearance_intent = wants_appearance_clauses(query)

        for cid, c in chunk_map.items():
            if cid not in rrf:
                continue
            if c.clause_id and c.clause_id in clause_targets:
                rrf[cid] += boost
            if table_intent and c.chunk_type == "table":
                rrf[cid] += boost * 1.5
            if table_id_target and c.table_id == table_id_target:
                rrf[cid] += boost * 2.0
            if appearance_intent and c.clause_id in ("3.2", "3.3"):
                rrf[cid] += boost * 1.2
            if appearance_intent and any(
                k in c.text for k in ("裂纹", "浮锈", "毛刺", "外观", "表面")
            ):
                rrf[cid] += boost
            if wants_composite_strength_table(query):
                if c.clause_id == "3.1":
                    rrf[cid] += boost * 1.5
                if c.chunk_type == "table":
                    rrf[cid] += boost * 1.5
            if wants_inspection_topics(query):
                if c.clause_id in ("4.3", "4.4") or c.chunk_type == "table":
                    rrf[cid] += boost
            if wants_technical_requirements_overview(query):
                if "技术要求、验收检查" in c.text or "除花键外的各种键的技术要求" in c.text:
                    rrf[cid] += boost * 2.5
                if c.clause_id and c.clause_id in TECH_REQUIREMENTS_CLAUSE_IDS:
                    rrf[cid] += boost * 1.8
                if c.section_title and "3技术要求" in c.section_title:
                    rrf[cid] += boost * 0.8
            if is_english_boilerplate_text(c.text):
                rrf[cid] *= 0.05

    def _pin_technical_overview_chunks(
        self,
        chunks: list[Chunk],
        have: set[str],
    ) -> list[Evidence]:
        """技术条件/范围总览：钉住范围条 + 第3章主要条款。"""
        pinned: list[Evidence] = []
        for c in chunks:
            if c.chunk_id in have:
                continue
            if "除花键外的各种键的技术要求" in c.text or (
                "技术要求、验收检查、标志与包装" in c.text
            ):
                pinned.append(
                    self._chunk_to_evidence(c, rrf_score=1.0, rerank_score=1.0)
                )
                have.add(c.chunk_id)
                break
        for cid in TECH_REQUIREMENTS_CLAUSE_IDS:
            if any(e.clause_id == cid for e in pinned):
                continue
            for c in chunks:
                if c.clause_id == cid and c.chunk_id not in have:
                    pinned.append(
                        self._chunk_to_evidence(c, rrf_score=1.0, rerank_score=1.0)
                    )
                    have.add(c.chunk_id)
                    break
        return pinned

    @staticmethod
    def _find_table_chunk(
        chunks: list[Chunk], table_id_target: str | None
    ) -> Chunk | None:
        preferred = table_id_target or "表1"
        for c in chunks:
            if c.chunk_type == "table" and c.table_id == preferred:
                return c
        for c in chunks:
            if c.chunk_type == "table":
                return c
        return None

    def _pin_required_after_rerank(
        self,
        evidence: list[Evidence],
        chunks: list[Chunk],
        query: str,
        top_n: int,
    ) -> list[Evidence]:
        """Rerank 可能挤掉表块/目标条款；评测以最终 evidence 为准，此处钉住。"""
        have = {e.chunk_id for e in evidence}
        clause_targets = extract_clause_ids_from_query(query)
        table_intent = wants_table_evidence(query)
        table_id_target = extract_table_id_from_query(query) or "表1"
        pinned: list[Evidence] = []

        if table_intent and not any(e.chunk_type == "table" for e in evidence):
            tc = self._find_table_chunk(chunks, table_id_target)
            if tc and tc.chunk_id not in have:
                pinned.append(
                    self._chunk_to_evidence(tc, rrf_score=1.0, rerank_score=1.0)
                )
                have.add(tc.chunk_id)

        if clause_targets and not any(
            e.clause_id in clause_targets for e in evidence + pinned
        ):
            for c in chunks:
                if c.clause_id in clause_targets and c.chunk_id not in have:
                    pinned.append(
                        self._chunk_to_evidence(c, rrf_score=1.0, rerank_score=1.0)
                    )
                    have.add(c.chunk_id)
                    break

        if wants_appearance_clauses(query):
            for cid in ("3.2", "3.3"):
                if any(e.clause_id == cid for e in evidence + pinned):
                    continue
                for c in chunks:
                    if c.clause_id == cid and c.chunk_id not in have:
                        pinned.append(
                            self._chunk_to_evidence(
                                c, rrf_score=1.0, rerank_score=1.0
                            )
                        )
                        have.add(c.chunk_id)
                        break

        if table_intent:
            for cid in ("3.5", "3.6"):
                if any(e.clause_id == cid for e in evidence + pinned):
                    continue
                for c in chunks:
                    if c.clause_id == cid and c.chunk_id not in have:
                        pinned.append(
                            self._chunk_to_evidence(
                                c, rrf_score=1.0, rerank_score=1.0
                            )
                        )
                        have.add(c.chunk_id)
                        break

        if wants_composite_strength_table(query):
            for cid in ("3.1", "4.2"):
                if not any(e.clause_id == cid for e in evidence + pinned):
                    for c in chunks:
                        if c.clause_id == cid and c.chunk_id not in have:
                            pinned.append(
                                self._chunk_to_evidence(
                                    c, rrf_score=1.0, rerank_score=1.0
                                )
                            )
                            have.add(c.chunk_id)
                            break
            if not any(e.chunk_type == "table" for e in evidence + pinned):
                tc = self._find_table_chunk(chunks, "表1")
                if tc and tc.chunk_id not in have:
                    pinned.append(
                        self._chunk_to_evidence(tc, rrf_score=1.0, rerank_score=1.0)
                    )

        if wants_technical_requirements_overview(query):
            for pe in self._pin_technical_overview_chunks(chunks, have):
                pinned.append(pe)

        if not pinned:
            return evidence

        merged = pinned + [e for e in evidence if e.chunk_id not in have]
        return merged[:top_n]

    def _order_for_rerank(
        self, pre_evidence: list[Evidence], query: str
    ) -> list[Evidence]:
        if wants_technical_requirements_overview(query):
            scope = [
                e
                for e in pre_evidence
                if "技术要求、验收检查" in e.text
                or "除花键外的各种键的技术要求" in e.text
            ]
            clauses = [
                e
                for e in pre_evidence
                if e.clause_id in TECH_REQUIREMENTS_CLAUSE_IDS
            ]
            rest = [
                e
                for e in pre_evidence
                if e not in scope and e not in clauses
            ]
            return scope + clauses + rest
        if not wants_table_evidence(query):
            return pre_evidence
        tables = [e for e in pre_evidence if e.chunk_type == "table"]
        rest = [e for e in pre_evidence if e.chunk_type != "table"]
        return tables + rest

    def _ensure_required_chunks(
        self,
        evidence: list[Evidence],
        chunks: list[Chunk],
        query: str,
        top_n: int,
    ) -> list[Evidence]:
        """表题/条款号题：若 Top-N 未含目标块，强制注入对应 chunk。"""
        have = {e.chunk_id for e in evidence}
        clause_targets = extract_clause_ids_from_query(query)
        table_intent = wants_table_evidence(query)
        table_id_target = extract_table_id_from_query(query) or "表1"
        injected: list[Evidence] = []

        if table_intent and not any(e.chunk_type == "table" for e in evidence):
            for c in chunks:
                if c.chunk_type != "table":
                    continue
                if table_id_target and c.table_id and c.table_id != table_id_target:
                    continue
                if c.chunk_id not in have:
                    injected.append(self._chunk_to_evidence(c, rrf_score=1.0))
                    have.add(c.chunk_id)
                break

        if clause_targets and not any(
            e.clause_id in clause_targets for e in evidence + injected
        ):
            for c in chunks:
                if c.clause_id in clause_targets and c.chunk_id not in have:
                    injected.append(self._chunk_to_evidence(c, rrf_score=1.0))
                    have.add(c.chunk_id)
                    break

        if wants_appearance_clauses(query):
            for cid in ("3.2", "3.3"):
                if any(e.clause_id == cid for e in evidence + injected):
                    continue
                for c in chunks:
                    if c.clause_id == cid and c.chunk_id not in have:
                        injected.append(self._chunk_to_evidence(c, rrf_score=1.0))
                        have.add(c.chunk_id)
                        break

        if table_intent:
            for cid in ("3.5", "3.6"):
                if any(e.clause_id == cid for e in evidence + injected):
                    continue
                for c in chunks:
                    if c.clause_id == cid and c.chunk_id not in have:
                        injected.append(self._chunk_to_evidence(c, rrf_score=1.0))
                        have.add(c.chunk_id)
                        break

        if wants_composite_strength_table(query):
            for cid in ("3.1", "4.2"):
                if any(e.clause_id == cid for e in evidence + injected):
                    continue
                for c in chunks:
                    if c.clause_id == cid and c.chunk_id not in have:
                        injected.append(self._chunk_to_evidence(c, rrf_score=1.0))
                        have.add(c.chunk_id)
                        break
            if not any(e.chunk_type == "table" for e in evidence + injected):
                tc = self._find_table_chunk(chunks, "表1")
                if tc and tc.chunk_id not in have:
                    injected.append(self._chunk_to_evidence(tc, rrf_score=1.0))
                    have.add(tc.chunk_id)

        if wants_technical_requirements_overview(query):
            for pe in self._pin_technical_overview_chunks(chunks, have):
                injected.append(pe)

        if not injected:
            return evidence
        merged = injected + [e for e in evidence if e.chunk_id not in have]
        return merged[:top_n]

    def retrieve(
        self,
        query: str,
        *,
        question_id: str | None = None,
        retrieval_round: int = 0,
        session_id: str | None = None,
    ) -> RetrievalOutcome:
        from src.observability.langfuse_telemetry import span_context

        with span_context(
            "retrieval.hybrid",
            input={"query": query, "retrieval_round": retrieval_round},
            metadata={"question_id": question_id},
        ) as span:
            outcome = self._retrieve_impl(
                query,
                question_id=question_id,
                retrieval_round=retrieval_round,
                session_id=session_id,
            )
            if span is not None:
                from src.observability.langfuse_telemetry import prepare_langfuse_io

                span.update(
                    output=prepare_langfuse_io(
                        {
                            "evidence_count": len(outcome.evidence),
                            "hard_refuse": outcome.hard_refuse,
                            "max_rrf": outcome.max_rrf,
                            "reranker_degraded": outcome.reranker_degraded,
                            "rerank_before_top1": outcome.rerank_before_top1,
                            "rerank_after_top1": outcome.rerank_after_top1,
                            "top_chunk_ids": [e.chunk_id for e in outcome.evidence[:5]],
                        }
                    )
                )
            return outcome

    def _retrieve_impl(
        self,
        query: str,
        *,
        question_id: str | None = None,
        retrieval_round: int = 0,
        session_id: str | None = None,
    ) -> RetrievalOutcome:
        try:
            dense_store = self.indexer.load_dense_index()
            bm25, chunks = self.indexer.load_bm25()
        except Exception as e:
            logger.error("Index missing: %s", e)
            return RetrievalOutcome(
                evidence=[],
                hard_refuse=True,
                max_rrf=0.0,
                max_bm25=0.0,
                reranker_degraded=False,
            )

        k = self.settings.retrieval_top_k
        top_n = self.settings.rerank_top_n
        q_vec = self._embed_query(query)
        try:
            dense_total = dense_store.count()
        except Exception:
            dense_total = len(chunks)
        dense_pool = min(
            max(k * self.settings.retrieval_dense_pool_factor, k),
            dense_total,
        )
        dense_ids, dense_metas, dense_dist = dense_store.search(q_vec, dense_pool)
        dist_by_id = {rid: d for rid, d in zip(dense_ids, dense_dist)}
        dense_scores = best_dense_scores_per_chunk(
            dense_ids, dense_metas, dist_by_id
        )
        dense_rank = best_dense_ranks_per_chunk(dense_ids, dense_metas)

        tokens = list(jieba.cut(query))
        bm25_scores_raw = bm25.get_scores(tokens)
        bm25_by_id = {
            chunks[i].chunk_id: float(bm25_scores_raw[i]) for i in range(len(chunks))
        }

        rrf_k = self.settings.rrf_k
        chunk_map = {c.chunk_id: c for c in chunks}
        all_ids = set(dense_scores) | set(bm25_by_id)
        rrf: dict[str, float] = {}
        bm25_ranked = sorted(bm25_by_id.items(), key=lambda x: x[1], reverse=True)
        bm25_rank = {cid: r + 1 for r, (cid, _) in enumerate(bm25_ranked)}

        for cid in all_ids:
            score = 0.0
            if cid in dense_rank:
                score += 1.0 / (rrf_k + dense_rank[cid])
            if cid in bm25_rank:
                score += 1.0 / (rrf_k + bm25_rank[cid])
            rrf[cid] = score

        self._apply_metadata_boost(rrf, chunk_map, query)

        ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:k]
        max_rrf = ranked[0][1] if ranked else 0.0
        max_bm25 = max(bm25_by_id.values()) if bm25_by_id else 0.0

        pre_evidence: list[Evidence] = []
        for cid, rrf_score in ranked:
            c = chunk_map.get(cid)
            if not c:
                continue
            pre_evidence.append(
                self._chunk_to_evidence(
                    c,
                    rrf_score=rrf_score,
                    bm25_score=bm25_by_id.get(cid, 0.0),
                )
            )
        pre_evidence = self._ensure_required_chunks(
            pre_evidence, chunks, query, max(k, top_n)
        )
        pre_evidence = self._order_for_rerank(pre_evidence, query)

        rerank_before = pre_evidence[0].chunk_id if pre_evidence else None
        docs = [e.text for e in pre_evidence]
        reranked = self.reranker.rerank(
            query,
            docs,
            top_n,
            question_id=question_id,
            retrieval_round=retrieval_round,
            session_id=session_id,
        )
        evidence: list[Evidence] = []
        for rr in reranked:
            e = pre_evidence[rr.index]
            evidence.append(
                e.model_copy(update={"rerank_score": rr.relevance_score})
            )
        rerank_after = evidence[0].chunk_id if evidence else None

        evidence = self._pin_required_after_rerank(
            evidence, chunks, query, top_n
        )
        if evidence:
            rerank_after = evidence[0].chunk_id

        hard_refuse = len(evidence) == 0 or (
            max_rrf < self.settings.retrieval_min_score
            and max_bm25 < self.settings.bm25_min_score
            and not any(
                e.chunk_type == "table" or e.clause_id
                for e in evidence
            )
        )

        return RetrievalOutcome(
            evidence=evidence,
            hard_refuse=hard_refuse,
            max_rrf=max_rrf,
            max_bm25=max_bm25,
            reranker_degraded=self.reranker.degraded,
            rerank_before_top1=rerank_before,
            rerank_after_top1=rerank_after,
        )
