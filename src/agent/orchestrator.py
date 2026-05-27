from __future__ import annotations

import logging
import uuid
from pathlib import Path

from src.agent.ingest_progress import (
    ProgressCallback,
    STEP_CHECK,
    STEP_PERSIST,
    noop_progress,
    report_progress,
)
from src.agent.query_graph import run_query
from src.agent.trace import run_query_with_trace
from src.config.settings import get_settings
from src.indexing.indexer import DocumentIndexer
from src.models.agent import AgentState
from src.pdf.structure import IngestError, build_document

logger = logging.getLogger(__name__)


def _backend_needs_mineru(backend: str) -> bool:
    b = (backend or "mineru").strip().lower()
    return b == "mineru"


def ingest(
    session_id: str | None = None,
    *,
    force_full: bool = False,
    on_progress: ProgressCallback | None = None,
) -> dict:
    """解析 PDF 并重建向量 + BM25 索引。

    force_full=True 时强制重跑 MinerU、重生成预设问句，并覆盖 FAISS/BM25
    （与 ``scripts/ingest.py`` 在 ``MINERU_FORCE_REPARSE=true`` 等配置下等价）。
    """
    progress = on_progress or noop_progress
    settings = get_settings()
    report_progress(progress, STEP_CHECK, "start")
    if force_full:
        settings = settings.model_copy(
            update={
                "mineru_force_reparse": True,
                "index_questions_force_regenerate": True,
            }
        )
        logger.info(
            "force_full ingest: reparse parsers + regenerate questions + rebuild index"
        )
    if force_full and _backend_needs_mineru(settings.pdf_parser_backend):
        from src.pdf.parsers.mineru import mineru_cli_available

        if not mineru_cli_available(
            settings.mineru_bin, settings.project_root
        ):
            report_progress(progress, STEP_CHECK, "error", "magic-pdf CLI 未安装")
            raise IngestError(
                "magic-pdf CLI 未安装。完整 ingest 需要 MinerU，请在本机终端执行：\n"
                "  bash scripts/setup.sh\n"
                "安装后重启 Streamlit，再点击「完整 ingest」。"
            )
    report_progress(progress, STEP_CHECK, "done")
    sid = session_id or f"ingest-{uuid.uuid4().hex[:8]}"
    manifest = build_document(
        settings=settings, session_id=sid, on_progress=progress
    )
    indexer = DocumentIndexer(settings)
    report_progress(progress, STEP_PERSIST, "start")
    manifest_path = indexer.persist_manifest(manifest)
    report_progress(progress, STEP_PERSIST, "done", str(manifest_path))
    meta = indexer.build_index(manifest, session_id=sid, on_progress=progress)
    return {
        "session_id": sid,
        "manifest_path": str(manifest_path),
        "chunk_count": len(manifest.chunks),
        "quality": manifest.quality,
        **meta,
    }


def _ensure_index() -> None:
    index_meta = get_settings().resolve_path(
        get_settings().faiss_index_dir
    ) / "index_meta.json"
    if not index_meta.exists():
        raise FileNotFoundError(
            "Index not found. Run: python scripts/ingest.py"
        )


def ask(
    question: str,
    question_id: str | None = None,
    session_id: str | None = None,
) -> AgentState:
    _ensure_index()
    return run_query(question, question_id=question_id, session_id=session_id)


def ask_with_trace(
    question: str,
    question_id: str | None = None,
    session_id: str | None = None,
) -> tuple[AgentState, list[dict]]:
    _ensure_index()
    return run_query_with_trace(
        question, question_id=question_id, session_id=session_id
    )


def index_ready() -> bool:
    faiss_dir = get_settings().resolve_path(get_settings().faiss_index_dir)
    return (faiss_dir / "index_meta.json").is_file() and (faiss_dir / "index.faiss").is_file()
