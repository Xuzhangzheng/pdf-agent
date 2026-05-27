from unittest.mock import MagicMock, patch

from src.agent.ingest_progress import (
    STEP_BM25,
    STEP_CHECK,
    STEP_PERSIST,
    build_ingest_plan,
)
from src.agent.orchestrator import ingest
from src.config.settings import get_settings
from src.models.blocks import DocManifest


def _empty_manifest() -> DocManifest:
    return DocManifest(
        doc_id="test",
        source_pdf="x.pdf",
        page_count=1,
        chunks=[],
        blocks=[],
        quality={"passed": True},
    )


def test_build_ingest_plan_omits_questions_when_disabled():
    s = get_settings().model_copy(update={"index_hypothetical_questions": False})
    ids = [step.id for step in build_ingest_plan(s)]
    assert "questions" not in ids
    assert "embed" in ids
    assert ids[-1] == STEP_BM25


def test_ingest_on_progress_order_force_full():
    events: list[tuple[str, str, str | None]] = []

    def on_progress(step_id: str, phase: str, detail: str | None = None) -> None:
        events.append((step_id, phase, detail))

    captured_progress: list = []

    def fake_build_document(*, settings, session_id, on_progress=None):
        captured_progress.append(on_progress)
        return _empty_manifest()

    def fake_build_index(manifest, session_id=None, *, on_progress=None):
        from src.agent.ingest_progress import STEP_BM25, STEP_EMBED, STEP_FAISS, report_progress

        report_progress(on_progress, STEP_EMBED, "start")
        report_progress(on_progress, STEP_EMBED, "done")
        report_progress(on_progress, STEP_FAISS, "start")
        report_progress(on_progress, STEP_FAISS, "done")
        report_progress(on_progress, STEP_BM25, "start")
        report_progress(on_progress, STEP_BM25, "done")
        return {"chunk_count": 0, "vector_row_count": 0}

    indexer = MagicMock()
    indexer.persist_manifest.return_value = get_settings().resolve_path(
        "artifacts/parsed/doc.json"
    )
    indexer.build_index.side_effect = fake_build_index

    with patch(
        "src.pdf.parsers.mineru.mineru_cli_available", return_value=True
    ), patch(
        "src.agent.orchestrator.build_document", side_effect=fake_build_document
    ), patch("src.agent.orchestrator.DocumentIndexer", return_value=indexer):
        ingest(session_id="ingest-prog01", force_full=True, on_progress=on_progress)

    step_ids = [e[0] for e in events if e[1] == "start"]
    assert step_ids[0] == STEP_CHECK
    assert STEP_PERSIST in step_ids
    assert step_ids.index(STEP_CHECK) < step_ids.index(STEP_PERSIST)
    assert events[-1] == (STEP_BM25, "done", None)
    assert captured_progress[0] is on_progress
    indexer.build_index.assert_called_once()
    call_kw = indexer.build_index.call_args.kwargs
    assert call_kw.get("on_progress") is on_progress
