from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from src.config.settings import Settings
from src.pdf.parsers.base import ParseOutput

logger = logging.getLogger(__name__)


class DoclingError(RuntimeError):
    pass


def _cache_dir(settings: Settings, stem: str) -> Path:
    return settings.resolve_path(settings.docling_output_dir) / stem


def _cache_valid(
    pdf: Path, cache: Path, page_count: int, settings: Settings
) -> bool:
    meta_path = cache / "meta.json"
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if meta.get("docling_ocr_engine") != settings.docling_ocr_engine:
        return False
    if meta.get("docling_images_scale") != settings.docling_images_scale:
        return False
    if meta.get("page_count") != page_count:
        return False
    if meta.get("pdf_mtime") != pdf.stat().st_mtime:
        return False
    for i in range(1, page_count + 1):
        if not (cache / f"page_{i:03d}.md").exists():
            return False
    return True


def _load_cached_pages(cache: Path, page_count: int) -> list[tuple[int, str]]:
    pages: list[tuple[int, str]] = []
    for i in range(1, page_count + 1):
        p = cache / f"page_{i:03d}.md"
        pages.append((i, p.read_text(encoding="utf-8", errors="replace")))
    return pages


def _page_count_from_document(document) -> int:
    pages = getattr(document, "pages", None)
    if pages is None:
        return 0
    try:
        return len(pages)
    except TypeError:
        return len(list(pages))


def _export_pages_markdown(document, page_count: int) -> list[tuple[int, str]]:
    n = _page_count_from_document(document) or page_count
    if n <= 0:
        full = document.export_to_markdown()
        return [(1, full)] if full.strip() else []

    out: list[tuple[int, str]] = []
    for page_no in range(1, n + 1):
        try:
            md = document.export_to_markdown(page_no=page_no)
        except TypeError:
            md = document.export_to_markdown()
            return [(page_no, md)] if md.strip() else []
        out.append((page_no, md or ""))

    if page_count > n:
        last_text = out[-1][1] if out else ""
        for p in range(n + 1, page_count + 1):
            out.append((p, last_text))
    return out


def _build_ocr_options(settings: Settings):
    """构建 OCR 选项。macOS 上 Docling 默认 auto→ocrmac，不适合中文扫描件。"""
    from docling.datamodel.pipeline_options import (
        EasyOcrOptions,
        OcrAutoOptions,
        OcrMacOptions,
        RapidOcrOptions,
    )

    engine = (settings.docling_ocr_engine or "rapidocr").strip().lower()
    force_ocr = True  # 扫描件无文本层，必须整页 OCR

    thresh = settings.docling_bitmap_area_threshold
    if engine == "auto":
        return OcrAutoOptions(
            force_full_page_ocr=force_ocr, bitmap_area_threshold=thresh
        )
    if engine == "ocrmac":
        return OcrMacOptions(
            lang=["zh-Hans", "en-US"],
            force_full_page_ocr=force_ocr,
            recognition="accurate",
            bitmap_area_threshold=thresh,
        )
    if engine == "easyocr":
        return EasyOcrOptions(
            lang=["ch_sim", "en"],
            force_full_page_ocr=force_ocr,
            bitmap_area_threshold=thresh,
        )
    if engine == "rapidocr":
        return RapidOcrOptions(
            lang=["chinese", "english"],
            backend="onnxruntime",
            force_full_page_ocr=force_ocr,
            bitmap_area_threshold=settings.docling_bitmap_area_threshold,
        )
    raise DoclingError(
        f"Unknown DOCLING_OCR_ENGINE={settings.docling_ocr_engine!r}. "
        "Use rapidocr | easyocr | ocrmac | auto."
    )


def _build_docling_converter(settings: Settings):
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as e:
        raise DoclingError(
            "Docling 未安装。请执行: pip install -r requirements-docling.txt "
            "或 bash scripts/install_docling.sh"
        ) from e

    ocr_options = _build_ocr_options(settings)
    scale = max(1.0, min(float(settings.docling_images_scale), 4.0))
    pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        ocr_options=ocr_options,
        images_scale=scale,
    )
    logger.info(
        "Docling pipeline: ocr_engine=%s kind=%s images_scale=%s",
        settings.docling_ocr_engine,
        getattr(ocr_options, "kind", type(ocr_options).__name__),
        scale,
    )
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )


def _convert_with_docling(pdf: Path, settings: Settings):
    converter = _build_docling_converter(settings)
    t0 = time.perf_counter()
    result = converter.convert(source=str(pdf.resolve()))
    elapsed = int((time.perf_counter() - t0) * 1000)
    if result is None or getattr(result, "document", None) is None:
        raise DoclingError("Docling convert returned empty document")
    logger.info("Docling convert finished in %dms", elapsed)
    return result, elapsed


def run_docling_parser(pdf: Path, page_count: int, settings: Settings) -> ParseOutput:
    cache = _cache_dir(settings, pdf.stem)
    if not settings.docling_force_reparse and _cache_valid(
        pdf, cache, page_count, settings
    ):
        logger.info("Reuse Docling cache at %s", cache)
        page_mds = _load_cached_pages(cache, page_count)
        meta = json.loads((cache / "meta.json").read_text(encoding="utf-8"))
        return ParseOutput(
            backend="docling",
            page_mds=page_mds,
            md_root=cache,
            artifacts_dir=cache,
            meta=meta,
        )

    result, elapsed_ms = _convert_with_docling(pdf, settings)
    document = result.document
    page_mds = _export_pages_markdown(document, page_count)

    if not page_mds:
        full_md = document.export_to_markdown()
        page_mds = [(i + 1, full_md) for i in range(page_count)]

    cache.mkdir(parents=True, exist_ok=True)
    for page_no, md in page_mds:
        (cache / f"page_{page_no:03d}.md").write_text(md, encoding="utf-8")
    full_md = document.export_to_markdown()
    (cache / "full.md").write_text(full_md, encoding="utf-8")

    meta = {
        "backend": "docling",
        "docling_ocr_engine": settings.docling_ocr_engine,
        "docling_images_scale": settings.docling_images_scale,
        "page_count": page_count,
        "pdf_mtime": pdf.stat().st_mtime,
        "convert_ms": elapsed_ms,
        "docling_pages": _page_count_from_document(document),
    }
    (cache / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return ParseOutput(
        backend="docling",
        page_mds=page_mds,
        md_root=cache,
        artifacts_dir=cache,
        meta=meta,
    )
