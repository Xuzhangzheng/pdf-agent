from __future__ import annotations

import json
import logging
from pathlib import Path

from src.config.settings import Settings
from src.pdf.fusion import fuse_document_pages
from src.pdf.ocr_postprocess import detect_clause_gaps
from src.pdf.parsers.base import ParseOutput
from src.pdf.parsers.docling_backend import run_docling_parser
from src.pdf.parsers.mineru_backend import run_mineru_parser
from src.pdf.vl_corrector import VlPageCorrector

logger = logging.getLogger(__name__)


def run_fusion_parser(
    pdf: Path,
    page_count: int,
    settings: Settings,
    *,
    session_id: str | None = None,
) -> ParseOutput:
    logger.info("Fusion: running MinerU + Docling for %s", pdf.name)
    mineru_out = run_mineru_parser(pdf, page_count, settings)
    docling_out = run_docling_parser(pdf, page_count, settings)

    fused_pages, fusion_report = fuse_document_pages(
        mineru_out.page_mds,
        docling_out.page_mds,
        page_count,
    )

    corrector = VlPageCorrector(settings)
    vl_pages: list[int] = []
    mineru_map = {p: t for p, t in mineru_out.page_mds}
    docling_map = {p: t for p, t in docling_out.page_mds}
    final_pages: list[tuple[int, str]] = []

    for page_num, fused_md in fused_pages:
        page_info = next(
            (x for x in fusion_report["pages"] if x["page"] == page_num),
            {},
        )
        disagreements = page_info.get("disagreements", [])
        gaps = page_info.get("gaps_after_fuse", []) or detect_clause_gaps(fused_md)

        text = fused_md
        if corrector.should_correct_page(
            disagreements=disagreements, gaps=gaps
        ):
            try:
                text = corrector.correct_page(
                    pdf,
                    page_num,
                    mineru_map.get(page_num, ""),
                    docling_map.get(page_num, ""),
                    fused_md,
                    session_id=session_id,
                )
                vl_pages.append(page_num)
                page_info["vl_corrected"] = True
            except Exception as e:
                logger.warning("VL correct page %s failed: %s", page_num, e)
                page_info["vl_error"] = str(e)

        final_pages.append((page_num, text))

    artifacts = settings.resolve_path(settings.parsed_output_dir) / "fusion"
    artifacts.mkdir(parents=True, exist_ok=True)
    report_path = artifacts / f"{pdf.stem}_fusion_report.json"
    fusion_report["vl_corrected_pages"] = vl_pages
    report_path.write_text(
        json.dumps(fusion_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    meta = {
        "backend": "fusion",
        "fusion_report": str(report_path),
        "mineru_meta": mineru_out.meta,
        "docling_meta": docling_out.meta,
        "vl_corrected_pages": vl_pages,
        **fusion_report.get("summary", {}),
    }

    return ParseOutput(
        backend="fusion",
        page_mds=final_pages,
        md_root=artifacts,
        artifacts_dir=artifacts,
        meta=meta,
    )
