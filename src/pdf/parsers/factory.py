from __future__ import annotations

import logging
from pathlib import Path

from src.config.settings import Settings
from src.pdf.parsers.base import ParseOutput
from src.pdf.parsers.docling_backend import DoclingError, run_docling_parser
from src.pdf.parsers.fusion_backend import run_fusion_parser
from src.pdf.parsers.mineru_backend import run_mineru_parser

logger = logging.getLogger(__name__)

# 方案 B：Docling（表格/正文一体，本地开源）
_SCHEME_B_ALIASES = frozenset({"docling", "scheme_b", "scheme-b", "b"})
_FUSION_ALIASES = frozenset({"fusion", "dual", "both", "merge"})


class ParserFactoryError(RuntimeError):
    pass


def normalize_parser_backend(raw: str) -> str:
    v = (raw or "mineru").strip().lower()
    if v in _SCHEME_B_ALIASES:
        return "docling"
    if v in _FUSION_ALIASES:
        return "fusion"
    if v == "mineru":
        return "mineru"
    raise ParserFactoryError(
        f"Unknown PDF_PARSER_BACKEND={raw!r}. "
        f"Use mineru | docling | fusion (双通道融合)."
    )


def run_pdf_parser(
    pdf: Path,
    page_count: int,
    settings: Settings,
    *,
    session_id: str | None = None,
) -> ParseOutput:
    backend = normalize_parser_backend(settings.pdf_parser_backend)
    logger.info("PDF parser backend=%s path=%s", backend, pdf)

    if backend == "mineru":
        return run_mineru_parser(pdf, page_count, settings)
    if backend == "docling":
        try:
            return run_docling_parser(pdf, page_count, settings)
        except DoclingError:
            raise
        except Exception as e:
            raise ParserFactoryError(f"Docling parser failed: {e}") from e
    if backend == "fusion":
        try:
            return run_fusion_parser(
                pdf, page_count, settings, session_id=session_id
            )
        except DoclingError as e:
            raise ParserFactoryError(f"Fusion/docling failed: {e}") from e
        except Exception as e:
            raise ParserFactoryError(f"Fusion parser failed: {e}") from e

    raise ParserFactoryError(f"Unsupported backend: {backend}")
