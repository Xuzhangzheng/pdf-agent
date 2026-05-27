from __future__ import annotations

import logging
from pathlib import Path

from src.agent.ingest_progress import (
    ProgressCallback,
    STEP_MINERU,
    report_progress,
)
from src.config.settings import Settings
from src.pdf.parsers.base import ParseOutput
from src.pdf.parsers.mineru import (
    MinerUError,
    load_mineru_pages,
    run_mineru,
)

logger = logging.getLogger(__name__)


def _locate_md_root_from_candidate(cand: Path) -> Path:
    md_files = sorted(cand.rglob("*.md"))
    if not md_files:
        return cand
    if len(md_files) == 1:
        return md_files[0].parent
    return cand


def resolve_mineru_md_root(
    pdf: Path,
    out_dir: Path,
    settings: Settings,
    *,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """若已有 MinerU 产物则复用（除非 MINERU_FORCE_REPARSE=true）。"""
    stem = pdf.stem
    if settings.mineru_force_reparse:
        logger.info("MINERU_FORCE_REPARSE=true, re-running MinerU OCR")
        report_progress(
            on_progress,
            STEP_MINERU,
            "start",
            "强制重跑 magic-pdf，通常需数分钟…",
        )
        try:
            root = run_mineru(pdf, out_dir / stem, settings.mineru_bin)
        except Exception:
            report_progress(on_progress, STEP_MINERU, "error")
            raise
        report_progress(on_progress, STEP_MINERU, "done", str(root))
        return root

    candidates = [
        out_dir / stem,
        out_dir / "magic-pdf" / stem / "ocr",
        out_dir / stem / stem,
        out_dir / stem / stem / stem,
    ]
    for cand in candidates:
        if cand.exists() and list(cand.rglob("*.md")):
            logger.info("Reuse MinerU output at %s", cand)
            report_progress(
                on_progress,
                STEP_MINERU,
                "start",
                f"复用已有产物: {cand.name}",
            )
            root = _locate_md_root_from_candidate(cand)
            report_progress(on_progress, STEP_MINERU, "done", "已复用缓存")
            return root
    report_progress(
        on_progress,
        STEP_MINERU,
        "start",
        "未找到缓存，运行 magic-pdf（通常需数分钟）…",
    )
    try:
        root = run_mineru(pdf, out_dir / stem, settings.mineru_bin)
    except Exception:
        report_progress(on_progress, STEP_MINERU, "error")
        raise
    report_progress(on_progress, STEP_MINERU, "done", str(root))
    return root


def run_mineru_parser(
    pdf: Path,
    page_count: int,
    settings: Settings,
    *,
    on_progress: ProgressCallback | None = None,
) -> ParseOutput:
    out_dir = settings.resolve_path(settings.mineru_output_dir)
    md_root = resolve_mineru_md_root(pdf, out_dir, settings, on_progress=on_progress)
    page_mds = load_mineru_pages(md_root, page_count)
    return ParseOutput(
        backend="mineru",
        page_mds=page_mds,
        md_root=md_root,
        artifacts_dir=md_root,
        meta={
            "mineru_model_mode": settings.mineru_model_mode,
            "mineru_output_dir": str(out_dir),
        },
    )
