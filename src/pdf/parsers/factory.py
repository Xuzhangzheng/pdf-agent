from __future__ import annotations

import logging
from pathlib import Path

from src.agent.ingest_progress import ProgressCallback
from src.config.settings import Settings
from src.pdf.parsers.base import ParseOutput
from src.pdf.parsers.mineru_backend import run_mineru_parser

logger = logging.getLogger(__name__)

_REMOVED_BACKENDS = frozenset(
    {
        "docling",
        "scheme_b",
        "scheme-b",
        "b",
        "fusion",
        "dual",
        "both",
        "merge",
    }
)


class ParserFactoryError(RuntimeError):
    pass


def normalize_parser_backend(raw: str) -> str:
    v = (raw or "mineru").strip().lower()
    if v in _REMOVED_BACKENDS:
        raise ParserFactoryError(
            f"PDF_PARSER_BACKEND={raw!r} 已移除（项目仅保留 MinerU 单通道）。"
            "请设置 PDF_PARSER_BACKEND=mineru。"
        )
    if v == "mineru":
        return "mineru"
    raise ParserFactoryError(
        f"Unknown PDF_PARSER_BACKEND={raw!r}. Use mineru."
    )


def run_pdf_parser(
    pdf: Path,
    page_count: int,
    settings: Settings,
    *,
    session_id: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> ParseOutput:
    backend = normalize_parser_backend(settings.pdf_parser_backend)
    logger.info("PDF parser backend=%s path=%s", backend, pdf)
    return run_mineru_parser(
        pdf, page_count, settings, on_progress=on_progress
    )
