#!/usr/bin/env python3
"""P0.5: MinerU POC on GBT PDF; print quality stats for structure-spec appendix."""
from __future__ import annotations

import json
import logging
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config.settings import get_settings
from src.pdf.detector import detect_pdf_type
from src.pdf.parsers.mineru import MinerUError, load_mineru_pages, run_mineru
from src.pdf.structure import parse_page_markdown, run_quality_gates, split_table_blocks

logging.basicConfig(level=logging.INFO)


def main() -> int:
    settings = get_settings()
    pdf = settings.resolve_path(settings.pdf_input_path)
    if not pdf.exists():
        print(f"PDF missing: {pdf}", file=sys.stderr)
        return 1

    det = detect_pdf_type(pdf)
    print("Detection:", det)

    out = settings.resolve_path(settings.mineru_output_dir) / pdf.stem
    try:
        md_root = run_mineru(pdf, out, settings.mineru_bin)
    except MinerUError as e:
        print(f"MinerU POC failed: {e}", file=sys.stderr)
        print("Install: pip install 'magic-pdf[full]' and ensure magic-pdf is on PATH")
        return 2

    pages = load_mineru_pages(md_root, det.page_count)
    blocks = []
    for pnum, md in pages:
        blocks.extend(parse_page_markdown(pnum, md))
    blocks = split_table_blocks(blocks)
    q = run_quality_gates(blocks, det.page_count, settings)

    report = {
        "pdf": str(pdf),
        "page_count": det.page_count,
        "md_root": str(md_root),
        "pages_md": len(pages),
        "total_blocks": len(blocks),
        "table_blocks": q.table_blocks,
        "clause_blocks": q.clause_blocks,
        "total_text_chars": q.total_text_chars,
        "parse_coverage": q.parse_coverage,
        "quality_passed": q.passed,
        "errors": q.errors,
        "sample_clause_ids": [b.clause_id for b in blocks if b.clause_id][:5],
        "sample_table_ids": [b.table_id for b in blocks if b.table_id][:5],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    appendix = settings.resolve_path("docs/ingest/structure-spec.md")
    if q.passed:
        print("\nPOC passed. Update structure-spec.md appendix with values above.")
    else:
        print("\nPOC quality gates failed:", q.errors)
    return 0 if q.passed else 3


if __name__ == "__main__":
    sys.exit(main())
