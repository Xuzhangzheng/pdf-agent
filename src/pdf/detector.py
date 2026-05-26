from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)

PdfType = str  # scanned | text | mixed


@dataclass
class PdfDetectionResult:
    pdf_type: PdfType
    page_count: int
    chars_per_page: list[int]
    total_chars: int
    strategy: str


def detect_pdf_type(pdf_path: Path, text_threshold: int = 80) -> PdfDetectionResult:
    doc = fitz.open(pdf_path)
    chars_per_page: list[int] = []
    for page in doc:
        text = page.get_text("text") or ""
        chars_per_page.append(len(text.strip()))
    doc.close()
    total = sum(chars_per_page)
    page_count = len(chars_per_page)
    pages_with_text = sum(1 for c in chars_per_page if c >= text_threshold)

    if pages_with_text == 0:
        pdf_type = "scanned"
    elif pages_with_text == page_count:
        pdf_type = "text"
    else:
        pdf_type = "mixed"

    if pdf_type == "scanned":
        strategy = "mineru"
    elif pdf_type == "text":
        strategy = "pymupdf"
    else:
        strategy = "mineru"

    logger.info(
        "PDF detect: path=%s type=%s pages=%s chars=%s strategy=%s",
        pdf_path,
        pdf_type,
        page_count,
        total,
        strategy,
    )
    return PdfDetectionResult(
        pdf_type=pdf_type,
        page_count=page_count,
        chars_per_page=chars_per_page,
        total_chars=total,
        strategy=strategy,
    )
