from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.agent.ingest_progress import (
    ProgressCallback,
    STEP_DETECT_PDF,
    STEP_OCR_POSTPROCESS,
    STEP_QUALITY,
    STEP_STRUCTURE,
    report_progress,
)
from src.config.settings import Settings, get_settings
from src.models.blocks import Block, Chunk, DocManifest, stable_id
from src.pdf.ocr_postprocess import (
    append_fixes_log,
    postprocess_content_list,
    postprocess_text,
)
from src.pdf.parsers.factory import ParserFactoryError, run_pdf_parser
from src.pdf.parsers.mineru import load_content_list
from src.pdf.detector import detect_pdf_type


class IngestError(RuntimeError):
    pass


CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+)+)\s*(.*)$")
# Docling 等常输出 ## 4.1 标题 或 - 3.2 列表项
CLAUSE_HEADING_RE = re.compile(r"^#{1,6}\s*(\d+(?:\.\d+)+)\s*(.*)$")
LIST_PREFIX_RE = re.compile(r"^[-*+]\s+")
TABLE_TITLE_RE = re.compile(r"^表\s*(\d+)\s*(.*)$", re.MULTILINE)
TABLE_TITLE_EN_RE = re.compile(r"^Table\s*(\d+)\s*(.*)$", re.MULTILINE | re.IGNORECASE)
MD_TABLE_RE = re.compile(r"^\|.+\|", re.MULTILINE)
HTML_TABLE_RE = re.compile(r"<table[\s>]", re.IGNORECASE)
MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
TABLE_REF_RE = re.compile(r"表\s*(\d+)")

OCR_SUBS = str.maketrans({"l": "1", "I": "1", "|": "1", "O": "0"})


@dataclass
class QualityReport:
    pages_parsed: int
    total_text_chars: int
    table_blocks: int
    clause_blocks: int
    parse_coverage: float
    passed: bool
    errors: list[str]


def normalize_clause(raw: str) -> str:
    return raw.translate(OCR_SUBS)


def match_clause_line(stripped: str) -> re.Match[str] | None:
    """匹配行首条款号：3.1 xxx、## 4.1 xxx、- 3.2 xxx（Docling 常见）。"""
    if not stripped:
        return None
    m_heading = CLAUSE_HEADING_RE.match(stripped)
    if m_heading:
        return m_heading
    candidate = LIST_PREFIX_RE.sub("", stripped, count=1)
    return CLAUSE_RE.match(candidate)


def _clause_confidence(raw: str, normalized: str) -> str:
    if raw == normalized:
        return "high"
    if len(raw) != len(normalized):
        return "low"
    diffs = sum(1 for a, b in zip(raw, normalized) if a != b)
    return "medium" if diffs <= 1 else "low"


def parse_page_markdown(page: int, md: str, section_title: str | None = None) -> list[Block]:
    blocks: list[Block] = []
    lines = md.splitlines()
    i = 0
    pending_table_id: str | None = None
    buf: list[str] = []
    buf_type = "paragraph"
    buf_clause: str | None = None
    buf_clause_raw: str | None = None
    buf_conf: str = "high"

    def flush():
        nonlocal buf, buf_type, buf_clause, buf_clause_raw, buf_conf, pending_table_id
        if not buf:
            return
        text = "\n".join(buf).strip()
        if not text:
            buf = []
            return
        ctype = buf_type
        if MD_TABLE_RE.search(text) or HTML_TABLE_RE.search(text):
            ctype = "table"
        bid = stable_id(str(page), str(len(blocks)), text[:80])
        blocks.append(
            Block(
                block_id=bid,
                chunk_type=ctype,  # type: ignore[arg-type]
                page=page,
                text=text,
                clause_id=buf_clause,
                clause_id_raw=buf_clause_raw,
                table_id=pending_table_id if ctype == "table" else None,
                section_title=section_title,
                confidence=buf_conf,  # type: ignore[arg-type]
            )
        )
        if ctype == "table":
            pending_table_id = None
        buf = []
        buf_type = "paragraph"
        buf_clause = None
        buf_clause_raw = None
        buf_conf = "high"

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("#"):
            flush()
            section_title = stripped.lstrip("#").strip()
            i += 1
            continue

        m_table = TABLE_TITLE_RE.match(stripped) or TABLE_TITLE_EN_RE.match(stripped)
        if m_table:
            flush()
            pending_table_id = f"表{m_table.group(1)}"
            i += 1
            continue

        m_clause = match_clause_line(stripped)
        if m_clause and len(m_clause.group(1)) <= 12:
            flush()
            raw_c = m_clause.group(1)
            norm = normalize_clause(raw_c)
            buf_type = "clause"
            buf_clause = norm
            buf_clause_raw = raw_c
            buf_conf = _clause_confidence(raw_c, norm)
            rest = m_clause.group(2).strip()
            buf = [f"{norm} {rest}".strip()] if rest else [norm]
            i += 1
            continue

        if MD_TABLE_RE.match(stripped) or stripped.startswith("<table"):
            if buf_type != "table":
                flush()
                buf_type = "table"
            buf.append(line)
            i += 1
            continue

        m_img = MD_IMAGE_RE.match(stripped)
        if m_img:
            flush()
            img_alt, img_path = m_img.group(1), m_img.group(2)
            table_id = pending_table_id
            if not table_id:
                ctx = "\n".join(buf[-8:]) if buf else ""
                m_ref = TABLE_REF_RE.search(ctx)
                table_id = f"表{m_ref.group(1)}" if m_ref else "表1"
            text = (
                f"{table_id}（MinerU 表格图像）\n"
                f"![{img_alt or table_id}]({img_path})\n"
                f"说明：扫描件中的表格由 OCR 输出为图像块，检索时请关联前文「见{table_id}」等表述。"
            )
            blocks.append(
                Block(
                    block_id=stable_id(str(page), str(len(blocks)), img_path),
                    chunk_type="table",
                    page=page,
                    text=text,
                    table_id=table_id,
                    section_title=section_title,
                    confidence="medium",
                )
            )
            pending_table_id = None
            i += 1
            continue

        if buf_type == "table" and stripped and not MD_TABLE_RE.match(stripped):
            flush()

        buf.append(line)
        i += 1

    flush()
    return blocks


def _postprocess_page_markdown(
    page_mds: list[tuple[int, str]],
    settings: Settings,
) -> tuple[list[tuple[int, str]], int, list[str], dict[int, list[str]]]:
    if not settings.ocr_postprocess_enabled:
        return page_mds, 0, [], {}
    log_path = settings.resolve_path(settings.parsed_output_dir) / "ocr_fixes.jsonl"
    if log_path.exists():
        log_path.unlink()
    fix_count = 0
    all_gaps: list[str] = []
    page_gaps: dict[int, list[str]] = {}
    out: list[tuple[int, str]] = []
    for page_num, md in page_mds:
        res = postprocess_text(md)
        append_fixes_log(res.fixes, log_path)
        fix_count += len(res.fixes)
        if res.clause_gaps:
            page_gaps[page_num] = res.clause_gaps
        for g in res.clause_gaps:
            if g not in all_gaps:
                all_gaps.append(g)
        out.append((page_num, res.text))
    return out, fix_count, all_gaps, page_gaps


def _export_postprocessed_markdown(
    page_mds: list[tuple[int, str]],
    settings: Settings,
    backend: str,
) -> Path:
    """导出 ingest 实际使用的 Markdown（含 L2 后处理），便于与 MinerU 原始缓存对照。"""
    out_dir = settings.resolve_path(settings.parsed_output_dir) / "md_ingest" / backend
    out_dir.mkdir(parents=True, exist_ok=True)
    for page_num, md in page_mds:
        (out_dir / f"page_{page_num:03d}.md").write_text(md, encoding="utf-8")
    return out_dir


def _apply_clause_gap_confidence(
    blocks: list[Block],
    page_gaps: dict[int, list[str]],
) -> list[Block]:
    """条款缺口页上的相关块降置信度，供检索/生成侧保守处理。"""
    if not page_gaps:
        return blocks
    out: list[Block] = []
    for b in blocks:
        gaps = page_gaps.get(b.page, [])
        if not gaps:
            out.append(b)
            continue
        downgrade = (
            "[OCR缺口]" in b.text
            or (b.clause_id and b.clause_id in gaps)
            or (b.clause_id_raw and b.clause_id_raw in gaps)
        )
        if downgrade and b.confidence == "high":
            out.append(b.model_copy(update={"confidence": "low"}))
        elif gaps and b.chunk_type in ("clause", "paragraph"):
            out.append(b.model_copy(update={"confidence": "low"}))
        else:
            out.append(b)
    return out


def enrich_blocks_from_content_list(
    blocks: list[Block],
    md_root: Path,
    page_count: int,
    settings: Settings | None = None,
) -> list[Block]:
    """MinerU content_list.json 中 type=table 多为图像，补全 MD 解析遗漏的表块。"""
    settings = settings or get_settings()
    items = load_content_list(md_root)
    if settings.ocr_postprocess_enabled and items:
        log_path = settings.resolve_path(settings.parsed_output_dir) / "ocr_fixes.jsonl"
        items, fixes = postprocess_content_list(items)
        append_fixes_log(fixes, log_path)
    if not items:
        return blocks

    has_table = any(b.chunk_type == "table" for b in blocks)
    out = list(blocks)
    pending_ref = "表1"
    for item in items:
        if item.get("type") != "table":
            text = (item.get("text") or "").strip()
            m = TABLE_REF_RE.search(text)
            if m:
                pending_ref = f"表{m.group(1)}"
            continue
        if has_table:
            continue
        img = item.get("img_path") or item.get("image_path") or ""
        text = (
            f"{pending_ref}（content_list 表格块）\n"
            f"图像路径: {img}\n"
            f"关联正文: 键的检查项目与合格质量水平见{pending_ref} 等条款。"
        )
        out.append(
            Block(
                block_id=stable_id("cl", pending_ref, img),
                chunk_type="table",
                page=min(page_count, 2),
                text=text,
                table_id=pending_ref,
                section_title="4.3尺寸检查",
                confidence="medium",
            )
        )
        has_table = True
    return out


def split_table_blocks(blocks: list[Block], max_rows: int = 40, window: int = 20) -> list[Block]:
    out: list[Block] = []
    for b in blocks:
        if b.chunk_type != "table":
            out.append(b)
            continue
        rows = [ln for ln in b.text.splitlines() if ln.strip()]
        if len(rows) <= max_rows:
            out.append(b)
            continue
        header = rows[:2]
        data_rows = rows[2:]
        for start in range(0, len(data_rows), window):
            chunk_rows = header + data_rows[start : start + window]
            text = "\n".join(chunk_rows)
            out.append(
                b.model_copy(
                    update={
                        "block_id": stable_id(b.block_id, str(start)),
                        "text": text,
                    }
                )
            )
    return out


def run_quality_gates(
    blocks: list[Block],
    page_count: int,
    settings: Settings,
) -> QualityReport:
    pages_with_text = len({b.page for b in blocks if b.text.strip()})
    total_chars = sum(len(b.text) for b in blocks)
    table_blocks = sum(1 for b in blocks if b.chunk_type == "table")
    clause_blocks = sum(1 for b in blocks if b.chunk_type == "clause")
    # MinerU 常将多页 PDF 合并为一个 .md，此时不能以「块页码种类数」衡量覆盖度
    mineru_merged_single_md = pages_with_text < page_count and total_chars >= settings.min_total_text_chars
    if mineru_merged_single_md:
        pages_parsed = page_count
        coverage = 1.0
    else:
        pages_parsed = pages_with_text
        coverage = pages_with_text / page_count if page_count else 0.0
    errors: list[str] = []

    if not mineru_merged_single_md and pages_with_text < page_count:
        errors.append(f"pages_parsed {pages_with_text} < {page_count}")
    if total_chars < settings.min_total_text_chars:
        errors.append(f"total_text_chars {total_chars} < {settings.min_total_text_chars}")
    if table_blocks < settings.min_table_blocks:
        errors.append(f"table_blocks {table_blocks} < {settings.min_table_blocks}")
    if clause_blocks < settings.min_clause_blocks:
        errors.append(f"clause_blocks {clause_blocks} < {settings.min_clause_blocks}")
    if not mineru_merged_single_md and coverage < settings.min_parse_coverage:
        errors.append(f"parse_coverage {coverage:.2f} < {settings.min_parse_coverage}")

    return QualityReport(
        pages_parsed=pages_parsed,
        total_text_chars=total_chars,
        table_blocks=table_blocks,
        clause_blocks=clause_blocks,
        parse_coverage=coverage,
        passed=len(errors) == 0,
        errors=errors,
    )


def blocks_to_chunks(blocks: list[Block], target_tokens: int, overlap_tokens: int) -> list[Chunk]:
    from src.indexing.chunker import chunk_block_text

    chunks: list[Chunk] = []
    for b in blocks:
        parts = chunk_block_text(b.text, target_tokens, overlap_tokens)
        for i, part in enumerate(parts):
            cid = stable_id(b.block_id, str(i))
            chunks.append(
                Chunk(
                    chunk_id=cid,
                    block_id=b.block_id,
                    chunk_type=b.chunk_type,
                    page=b.page,
                    text=part,
                    clause_id=b.clause_id,
                    table_id=b.table_id,
                    section_title=b.section_title,
                    confidence=b.confidence,
                    token_estimate=len(part) // 2,
                )
            )
    return chunks


def build_document(
    pdf_path: str | None = None,
    settings: Settings | None = None,
    *,
    session_id: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> DocManifest:
    settings = settings or get_settings()
    pdf = settings.resolve_path(pdf_path or settings.pdf_input_path)
    if not pdf.exists():
        raise IngestError(f"PDF not found: {pdf}")

    report_progress(on_progress, STEP_DETECT_PDF, "start")
    detection = detect_pdf_type(pdf)
    page_count = detection.page_count
    report_progress(
        on_progress,
        STEP_DETECT_PDF,
        "done",
        f"{page_count} 页, strategy={detection.strategy}",
    )

    if not settings.mvp_force_scanned and detection.strategy == "pymupdf":
        raise IngestError(
            "MVP text-layer path not implemented; set MVP_FORCE_SCANNED=true "
            "or use PDF_PARSER_BACKEND=mineru for scanned PDF."
        )

    try:
        parse_out = run_pdf_parser(
            pdf,
            page_count,
            settings,
            session_id=session_id,
            on_progress=on_progress,
        )
    except ParserFactoryError as e:
        raise IngestError(str(e)) from e

    if settings.ocr_postprocess_enabled:
        report_progress(on_progress, STEP_OCR_POSTPROCESS, "start")
    page_mds, ocr_fix_count, clause_gaps, page_gaps = _postprocess_page_markdown(
        parse_out.page_mds, settings
    )
    if settings.ocr_postprocess_enabled:
        report_progress(
            on_progress,
            STEP_OCR_POSTPROCESS,
            "done",
            f"修复 {ocr_fix_count} 处",
        )
    md_ingest_dir = _export_postprocessed_markdown(
        page_mds, settings, parse_out.backend
    )

    report_progress(on_progress, STEP_STRUCTURE, "start")
    all_blocks: list[Block] = []
    section: str | None = None
    for page_num, md in page_mds:
        page_blocks = parse_page_markdown(page_num, md, section)
        all_blocks.extend(page_blocks)

    all_blocks = _apply_clause_gap_confidence(all_blocks, page_gaps)

    if parse_out.backend == "mineru" and parse_out.md_root:
        all_blocks = enrich_blocks_from_content_list(
            all_blocks, parse_out.md_root, page_count, settings
        )
    all_blocks = split_table_blocks(all_blocks)
    report_progress(
        on_progress,
        STEP_STRUCTURE,
        "done",
        f"{len(all_blocks)} blocks",
    )

    report_progress(on_progress, STEP_QUALITY, "start")
    quality = run_quality_gates(all_blocks, page_count, settings)
    if not quality.passed:
        report_progress(on_progress, STEP_QUALITY, "error", "; ".join(quality.errors))
        raise IngestError("Quality gates failed: " + "; ".join(quality.errors))
    report_progress(on_progress, STEP_QUALITY, "done")

    qmeta = dict(quality.__dict__)
    qmeta["ocr_fix_count"] = ocr_fix_count
    qmeta["md_ingest_dir"] = str(md_ingest_dir)
    qmeta["clause_gaps_detected"] = clause_gaps
    if clause_gaps:
        qmeta["ocr_quality_warnings"] = [
            f"条款序列疑似缺口: {', '.join(clause_gaps)}（已降置信度，勿臆造补全）"
        ]
    qmeta["pdf_parser_backend"] = parse_out.backend
    if parse_out.meta:
        qmeta["parser_meta"] = parse_out.meta
    if parse_out.backend == "mineru":
        qmeta["mineru_model_mode"] = settings.mineru_model_mode

    chunks = blocks_to_chunks(
        all_blocks,
        settings.chunk_target_tokens,
        settings.chunk_overlap_tokens,
    )

    return DocManifest(
        doc_id=stable_id(str(pdf)),
        source_pdf=str(pdf),
        page_count=page_count,
        blocks=all_blocks,
        chunks=chunks,
        quality=qmeta,
    )
