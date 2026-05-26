from __future__ import annotations

import logging
from pathlib import Path

from src.agent.query_graph import run_query
from src.config.settings import get_settings
from src.indexing.indexer import DocumentIndexer
from src.models.agent import AgentState
from src.pdf.structure import build_document

logger = logging.getLogger(__name__)


def ingest(session_id: str | None = None) -> dict:
    settings = get_settings()
    manifest = build_document(settings=settings, session_id=session_id)
    indexer = DocumentIndexer(settings)
    manifest_path = indexer.persist_manifest(manifest)
    meta = indexer.build_index(manifest, session_id=session_id)
    return {
        "manifest_path": str(manifest_path),
        "chunk_count": len(manifest.chunks),
        "quality": manifest.quality,
        **meta,
    }


def ask(
    question: str,
    question_id: str | None = None,
    session_id: str | None = None,
) -> AgentState:
    index_meta = get_settings().resolve_path(
        get_settings().chroma_persist_dir
    ) / "index_meta.json"
    if not index_meta.exists():
        raise FileNotFoundError(
            "Index not found. Run: python scripts/ingest.py"
        )
    return run_query(question, question_id=question_id, session_id=session_id)


def index_ready() -> bool:
    p = get_settings().resolve_path(get_settings().chroma_persist_dir) / "index_meta.json"
    return p.exists()
