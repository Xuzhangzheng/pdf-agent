from __future__ import annotations

import difflib
import json
import logging
import re
from dataclasses import dataclass, field

from src.pdf.ocr_postprocess import detect_clause_gaps, postprocess_text

logger = logging.getLogger(__name__)

# 避免 4.1.1 被 \b 截成 4.1（小数点前后都是“词字符”）
_CLAUSE_ID_RE = re.compile(r"^(\d+(?:\.\d+)*)(?=[^\d]|$)")


@dataclass
class PageFusionResult:
    page: int
    text: str
    mineru_chars: int
    docling_chars: int
    clause_ids: list[str]
    disagreements: list[str] = field(default_factory=list)
    recovered_from: dict[str, str] = field(default_factory=dict)
    channel_scores: dict[str, float] = field(default_factory=dict)


def _normalize_mineru_pages(
    page_mds: list[tuple[int, str]], page_count: int
) -> list[tuple[int, str]]:
    """MinerU 常把全文复制到每一页；融合时让每页都能访问全文条款。"""
    if not page_mds:
        return page_mds
    texts = [t for _, t in page_mds]
    if len(set(texts)) == 1 and page_count > 1:
        combined = texts[0]
        return [(i, combined) for i in range(1, page_count + 1)]
    return page_mds


def _strip_line_for_clause(line: str) -> str:
    stripped = line.strip()
    for prefix in ("- ", "* ", "+ "):
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
    if stripped.startswith("#"):
        return re.sub(r"^#{1,6}\s*", "", stripped).strip()
    return stripped


def _extract_clause_lines(md: str) -> dict[str, str]:
    """条款号 -> 文本（行首条款 + 段内嵌入条款，如 MinerU 连续段落）。"""
    out: dict[str, str] = {}
    for line in md.splitlines():
        stripped = _strip_line_for_clause(line)
        if not stripped:
            continue
        m = _CLAUSE_ID_RE.match(stripped)
        if not m:
            continue
        cid = m.group(1)
        if not _is_plausible_clause_id(cid):
            continue
        if cid not in out or len(stripped) > len(out[cid]):
            out[cid] = stripped

    for m in re.finditer(
        r"(\d+(?:\.\d+)+)(?=[^\d\n])",
        md,
    ):
        cid = m.group(1)
        if not _is_plausible_clause_id(cid):
            continue
        start = m.start()
        nxt = re.search(r"\n|\d+(?:\.\d+)+(?=[^\d\n])", md[start + len(cid) :])
        end = start + len(cid) + (nxt.start() if nxt else len(md[start:]))
        snippet = md[start:end].strip()
        if cid not in out or len(snippet) > len(out[cid]):
            out[cid] = snippet
    return out


def _line_quality_score(line: str) -> float:
    han = len(re.findall(r"[\u4e00-\u9fff]", line))
    bad = line.count("Ж") + line.count("™") + line.count("【")
    return han - bad * 5 + len(line) * 0.01


def _pick_clause_line(cid: str, mineru: str, docling: str) -> tuple[str, str | None]:
    """返回 (选中行, 来源 mineru|docling|merge|None)。"""
    if not mineru and not docling:
        return "", None
    if not mineru:
        return docling, "docling"
    if not docling:
        return mineru, "mineru"

    ratio = difflib.SequenceMatcher(None, mineru, docling).ratio()
    if ratio >= 0.82:
        return (mineru if _line_quality_score(mineru) >= _line_quality_score(docling) else docling), "merge"

    sm, sd = _line_quality_score(mineru), _line_quality_score(docling)
    if abs(sm - sd) < 3:
        return (mineru if len(mineru) >= len(docling) else docling), "merge"
    return (mineru if sm > sd else docling), ("mineru" if sm > sd else "docling")


def _is_plausible_clause_id(cid: str) -> bool:
    try:
        parts = [int(p) for p in cid.split(".")]
    except ValueError:
        return False
    return all(1 <= p <= 30 for p in parts)


def _filter_clause_ids(ids: list[str]) -> list[str]:
    """去掉 3、4 等孤号（当存在 3.1、4.1 等子条款时）及日期噪声。"""
    s = {i for i in ids if _is_plausible_clause_id(i)}
    out: list[str] = []
    for cid in sorted(s, key=lambda x: [int(p) for p in x.split(".")]):
        if "." in cid:
            out.append(cid)
            continue
        if any(x.startswith(f"{cid}.") for x in s):
            continue
        out.append(cid)
    return out


def _page_clause_prefix(page: int) -> str | None:
    if page == 3:
        return "3"
    if page >= 4:
        return "4"
    return None


def _non_clause_header_lines(md: str) -> list[str]:
    headers: list[str] = []
    for line in md.splitlines():
        s = line.strip()
        if not s:
            continue
        if _CLAUSE_ID_RE.match(s.lstrip("-#* ").strip()) or s.startswith("|"):
            continue
        if s.startswith("#") or "范围" in s or "引用文件" in s or "技术要求" in s:
            headers.append(line)
    return headers


def _merge_clause_dicts(
    m_clauses: dict[str, str],
    d_clauses: dict[str, str],
) -> tuple[dict[str, str], list[str], dict[str, str]]:
    all_ids = _filter_clause_ids(list(set(m_clauses) | set(d_clauses)))
    merged: dict[str, str] = {}
    disagreements: list[str] = []
    recovered: dict[str, str] = {}
    for cid in all_ids:
        line, _ = _pick_clause_line(
            cid, m_clauses.get(cid, ""), d_clauses.get(cid, "")
        )
        if line:
            merged[cid] = line
        if cid in m_clauses and cid in d_clauses:
            if (
                difflib.SequenceMatcher(
                    None, m_clauses[cid], d_clauses[cid]
                ).ratio()
                < 0.72
            ):
                disagreements.append(cid)
        elif cid in m_clauses:
            recovered[cid] = "mineru"
        elif cid in d_clauses:
            recovered[cid] = "docling"
    return merged, disagreements, recovered


def fuse_page_text(
    page: int,
    mineru_raw: str,
    docling_raw: str,
    global_merged: dict[str, str],
    global_disagreements: list[str],
    global_recovered: dict[str, str],
) -> PageFusionResult:
    d_pp = postprocess_text(docling_raw)
    d_clauses = _extract_clause_lines(d_pp.text)
    prefix = _page_clause_prefix(page)

    page_ids = _filter_clause_ids(list(d_clauses.keys()))
    if prefix:
        page_ids = _filter_clause_ids(
            list(
                set(page_ids)
                | {cid for cid in global_merged if cid.startswith(prefix + ".")}
            )
        )

    all_ids = page_ids

    fused_lines: list[str] = []
    for h in _non_clause_header_lines(d_pp.text):
        if h.strip().startswith("##") and h not in fused_lines:
            fused_lines.append(h)

    for cid in all_ids:
        line = global_merged.get(cid, "")
        if not line:
            continue
        fused_lines.append(f"- {line}" if not line.startswith("-") else line)

    body = "\n".join(fused_lines).strip()
    body = body + "\n" if body else ""

    page_disagree = [c for c in global_disagreements if c in all_ids]
    page_recovered = {k: v for k, v in global_recovered.items() if k in all_ids}

    return PageFusionResult(
        page=page,
        text=body,
        mineru_chars=len(mineru_raw),
        docling_chars=len(docling_raw),
        clause_ids=all_ids,
        disagreements=page_disagree,
        recovered_from=page_recovered,
        channel_scores={"merged_global": float(len(global_merged))},
    )


def fuse_document_pages(
    mineru_pages: list[tuple[int, str]],
    docling_pages: list[tuple[int, str]],
    page_count: int,
) -> tuple[list[tuple[int, str]], dict]:
    mineru_pages = _normalize_mineru_pages(mineru_pages, page_count)
    docling_map = {p: t for p, t in docling_pages}
    mineru_map = {p: t for p, t in mineru_pages}
    mineru_full = mineru_map.get(1, "")
    m_pp = postprocess_text(mineru_full)
    d_all: dict[str, str] = {}
    for p in range(1, page_count + 1):
        d_all.update(_extract_clause_lines(postprocess_text(docling_map.get(p, "")).text))
    m_clauses = _extract_clause_lines(m_pp.text)
    global_merged, global_disagree, global_recovered = _merge_clause_dicts(
        m_clauses, d_all
    )

    fused_pages: list[tuple[int, str]] = []
    report: dict = {"pages": [], "summary": {}}

    for p in range(1, page_count + 1):
        res = fuse_page_text(
            p,
            mineru_map.get(p, ""),
            docling_map.get(p, ""),
            global_merged,
            global_disagree,
            global_recovered,
        )
        fused_pages.append((p, res.text))
        report["pages"].append(
            {
                "page": p,
                "clause_ids": res.clause_ids,
                "disagreements": res.disagreements,
                "recovered_from": res.recovered_from,
                "gaps_after_fuse": detect_clause_gaps(res.text),
            }
        )

    report["summary"] = {
        "disagreement_count": len(global_disagree),
        "cross_channel_recovered_clauses": len(global_recovered),
        "global_clause_ids": list(global_merged.keys()),
    }
    return fused_pages, report
