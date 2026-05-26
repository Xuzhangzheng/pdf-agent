from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config.settings import Settings, get_settings
from src.indexing.dual_dense import (
    INDEX_ROLE_CONTENT,
    INDEX_ROLE_QUESTION,
    chroma_row_id_for_question,
)
from src.indexing.embedder import DashScopeEmbedder
from src.indexing.question_generator import generate_questions_for_chunks
from src.models.blocks import Chunk, DocManifest

logger = logging.getLogger(__name__)


class DocumentIndexer:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.embedder = DashScopeEmbedder(self.settings)
        self.collection_name = "pdf_agent_chunks"

    def persist_manifest(self, manifest: DocManifest) -> Path:
        out = self.settings.resolve_path(self.settings.parsed_output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "doc.json"
        path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path

    def _chunk_metadata(self, c: Chunk, *, index_role: str) -> dict:
        return {
            "page": c.page,
            "chunk_type": c.chunk_type,
            "clause_id": c.clause_id or "",
            "table_id": c.table_id or "",
            "block_id": c.block_id,
            "confidence": c.confidence,
            "chunk_id": c.chunk_id,
            "index_role": index_role,
        }

    def build_index(self, manifest: DocManifest, session_id: str | None = None) -> dict:
        chunks = manifest.chunks
        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict] = []

        for c in chunks:
            ids.append(c.chunk_id)
            texts.append(c.text)
            metadatas.append(self._chunk_metadata(c, index_role=INDEX_ROLE_CONTENT))

        question_map: dict[str, list[str]] = {}
        question_rows = 0
        if self.settings.index_hypothetical_questions:
            question_map = generate_questions_for_chunks(
                chunks,
                settings=self.settings,
                session_id=session_id,
                force_regenerate=self.settings.index_questions_force_regenerate,
            )
            for c in chunks:
                for i, q in enumerate(question_map.get(c.chunk_id, [])):
                    ids.append(chroma_row_id_for_question(c.chunk_id, i))
                    texts.append(q)
                    meta = self._chunk_metadata(c, index_role=INDEX_ROLE_QUESTION)
                    metadatas.append(meta)
                    question_rows += 1

        vectors = self.embedder.embed_texts(texts, session_id=session_id)

        chroma_dir = self.settings.resolve_path(self.settings.chroma_persist_dir)
        chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        try:
            client.delete_collection(self.collection_name)
        except Exception:
            pass
        collection = client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        collection.add(
            ids=ids,
            embeddings=vectors,
            documents=texts,
            metadatas=metadatas,
        )

        bm25_path = self._build_bm25(chunks)
        meta = {
            "chunk_count": len(chunks),
            "chroma_row_count": len(ids),
            "question_vector_count": question_rows,
            "dual_dense_enabled": self.settings.index_hypothetical_questions,
            "chroma_dir": str(chroma_dir),
            "bm25_path": str(bm25_path),
            "collection": self.collection_name,
            "questions_cache": str(
                self.settings.resolve_path(self.settings.parsed_output_dir)
                / "hypothetical_questions.json"
            ),
        }
        meta_path = chroma_dir / "index_meta.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        logger.info(
            "Index built: %d chunks, %d chroma rows (%d question vectors)",
            len(chunks),
            len(ids),
            question_rows,
        )
        return meta

    def _build_bm25(self, chunks: list[Chunk]) -> Path:
        import jieba
        from rank_bm25 import BM25Okapi

        tokenized = [list(jieba.cut(c.text)) for c in chunks]
        bm25 = BM25Okapi(tokenized)
        payload = {
            "bm25": bm25,
            "chunks": [c.model_dump() for c in chunks],
        }
        path = self.settings.resolve_path(self.settings.bm25_index_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(payload, f)
        return path

    def load_bm25(self) -> tuple:
        path = self.settings.resolve_path(self.settings.bm25_index_path)
        with path.open("rb") as f:
            payload = pickle.load(f)
        chunks = [Chunk.model_validate(c) for c in payload["chunks"]]
        return payload["bm25"], chunks

    def get_collection(self):
        chroma_dir = self.settings.resolve_path(self.settings.chroma_persist_dir)
        client = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        return client.get_collection(self.collection_name)
