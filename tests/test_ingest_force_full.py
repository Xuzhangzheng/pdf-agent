from unittest.mock import MagicMock, patch

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


def test_ingest_force_full_sets_reparse_flags():
    captured: dict = {}

    def fake_build_document(*, settings, session_id, on_progress=None):
        captured["settings"] = settings
        captured["session_id"] = session_id
        captured["on_progress"] = on_progress
        return _empty_manifest()

    indexer = MagicMock()
    indexer.persist_manifest.return_value = get_settings().resolve_path("artifacts/parsed/doc.json")
    indexer.build_index.return_value = {"chunk_count": 0}

    with patch(
        "src.pdf.parsers.mineru.mineru_cli_available", return_value=True
    ), patch(
        "src.agent.orchestrator.build_document", side_effect=fake_build_document
    ), patch("src.agent.orchestrator.DocumentIndexer", return_value=indexer):
        result = ingest(session_id="ingest-test01", force_full=True)

    s = captured["settings"]
    assert s.mineru_force_reparse is True
    assert s.index_questions_force_regenerate is True
    assert captured["session_id"] == "ingest-test01"
    assert result["session_id"] == "ingest-test01"
