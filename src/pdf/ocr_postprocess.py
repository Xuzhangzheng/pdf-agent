from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.pdf.table_postprocess import normalize_table_latex

logger = logging.getLogger(__name__)

_GAP_TAG = "[OCR缺口]"


@dataclass
class OcrFixLog:
    rule: str
    before: str
    after: str


@dataclass
class OcrPostprocessResult:
    text: str
    fixes: list[OcrFixLog] = field(default_factory=list)
    low_confidence: bool = False
    clause_gaps: list[str] = field(default_factory=list)


_PHRASE_FIXES = [
    ("华人民共和国国家标", "中华人民共和国国家标准"),
    ("中华人民共和国国家标", "中华人民共和国国家标准"),
]

_CLAUSE_GAP_RE = re.compile(r"(?<![0-9])3\.键")
_ORPHAN_去毛刺_RE = re.compile(r"^-\s*去毛刺[。.]?\s*$", re.MULTILINE)
_ORPHAN_412_TAIL_RE = re.compile(
    r"^-\s*成品质量符合相应标准的规定[。.]?\s*$", re.MULTILINE
)


def _apply_phrase_fixes(text: str, fixes: list[OcrFixLog]) -> str:
    for old, new in sorted(_PHRASE_FIXES, key=lambda p: -len(p[0])):
        if old not in text or new in text:
            continue
        fixes.append(OcrFixLog("phrase", old, new))
        text = text.replace(old, new, 1)
    return text


def _fix_clause_3_1(text: str, fixes: list[OcrFixLog]) -> str:
    if "3.2" not in text and "3.2键" not in text:
        return text
    if "3.1" in text or "3.1键" in text:
        return text

    def repl(m: re.Match) -> str:
        fixes.append(OcrFixLog("clause_sequence", "3.键", "3.1键"))
        return "3.1键"

    return _CLAUSE_GAP_RE.sub(repl, text, count=1)


def _fix_key_width_b_vs_6(text: str, fixes: list[OcrFixLog]) -> str:
    pairs = [
        ("键长L与键宽6", "键长L与键宽b"),
        ("键长L与键宽 6", "键长L与键宽 b"),
        ("键宽6面", "键宽b面"),
        ("键宽 6面", "键宽 b面"),
    ]
    for old, new in pairs:
        if old in text:
            fixes.append(OcrFixLog("key_width", old, new))
            text = text.replace(old, new)

    if "b≤6mm" in text or "b≤6 mm" in text:
        for old, new in [
            ("6≥8mm", "b≥8mm"),
            ("6≥40mm", "b≥40mm"),
            ("6≥8 mm", "b≥8 mm"),
            ("6≥40 mm", "b≥40 mm"),
        ]:
            if old in text:
                fixes.append(OcrFixLog("dim_grade_b_vs_6", old, new))
                text = text.replace(old, new)
    return text


def _fix_tolerance_plus_minus(text: str, fixes: list[OcrFixLog]) -> str:
    patterns = [
        ("极限偏差为土", "极限偏差为±"),
        ("偏差为土", "偏差为±"),
        ("为土AT", "为±AT"),
        ("为土 AT", "为±AT"),
    ]
    for old, new in patterns:
        if old in text:
            fixes.append(OcrFixLog("tolerance_symbol", old, new))
            text = text.replace(old, new)
    return text


def _fix_dash_in_standard_no(text: str, fixes: list[OcrFixLog]) -> str:
    patterns = [
        (r"(GB/T\s*1568)\s*一\s*(\d{4})", r"\1-\2"),
        (r"(GB/T\s*11334)\s*一+\s*(\d{4})", r"\1-\2"),
        (r"(GB/T\s*2828\.1)\s*一+\s*(\d{4})", r"\1-\2"),
        (r"(GB/T\s*1184)\s*一+\s*(\d{4})", r"\1-\2"),
    ]
    for pat, repl in patterns:
        new = re.sub(pat, repl, text)
        if new != text:
            fixes.append(OcrFixLog("standard_number_dash", "一→-", pat))
            text = new
    return text


def detect_clause_gaps(text: str) -> list[str]:
    """检测条款序列缺口（不补全条文，仅用于降置信度/拒答）。"""
    gaps: list[str] = []
    if re.search(r"3\.6", text) and not re.search(r"3\.7", text):
        if _ORPHAN_去毛刺_RE.search(text):
            gaps.append("3.7")
    if re.search(r"4\.1\.1", text) and not re.search(r"4\.1\.2", text):
        if re.search(r"4\.1\.3", text) and (
            _ORPHAN_412_TAIL_RE.search(text)
            or "4.1.2（OCR残缺）" in text
        ):
            gaps.append("4.1.2")
    return gaps


def _mark_clause_gaps(text: str, fixes: list[OcrFixLog]) -> str:
    """为疑似丢行打标，不写入标准外内容。"""
    gaps = detect_clause_gaps(text)
    if "3.7" in gaps and _ORPHAN_去毛刺_RE.search(text):
        tagged = f"- {_GAP_TAG} 去毛刺。（疑似缺失前置条款 3.7，请核对原件）"
        fixes.append(OcrFixLog("clause_gap_mark", "3.7", "tagged"))
        text = _ORPHAN_去毛刺_RE.sub(tagged, text)

    if "4.1.2" in gaps and _ORPHAN_412_TAIL_RE.search(text):
        new_line = (
            f"- {_GAP_TAG} 4.1.2（句尾残片）成品质量符合相应标准的规定。"
            "（疑似缺失条款前半，请核对原件）"
        )
        fixes.append(OcrFixLog("clause_gap_mark", "4.1.2", "tagged"))
        text = _ORPHAN_412_TAIL_RE.sub(new_line, text)

    return text


def _merge_split_411_line(text: str, fixes: list[OcrFixLog]) -> str:
    m = re.search(
        r"(-\s*4\.1\.1[^\n]+)\n(-\s*成品质量符合相应标准的规定[。.]?)\n(-\s*4\.1\.3)",
        text,
        re.MULTILINE,
    )
    if m and "4.1.2" not in text:
        replacement = (
            f"{m.group(1)}\n"
            f"- {_GAP_TAG} 4.1.2（句尾残片）{m.group(2).lstrip('- ').strip()}"
            f"（疑似缺失条款前半，请核对原件）\n"
            f"{m.group(3)}"
        )
        fixes.append(OcrFixLog("clause_split", "4.1.1/成品…/4.1.3", "tagged"))
        text = text[: m.start()] + replacement + text[m.end() :]
    return text


def _insert_newlines_after_period(text: str, fixes: list[OcrFixLog]) -> str:
    if "\n\n" in text or text.count("\n") > 3:
        return text
    if len(text) < 120 or text.count("。") < 2:
        return text
    new = re.sub(r"。(?!\n)", "。\n", text)
    if new != text:
        fixes.append(OcrFixLog("newline_after_period", "merged", "split_on_。"))
    return new


def _detect_garbled(text: str) -> bool:
    if not text or len(text.strip()) < 4:
        return True
    bad = len(re.findall(r"[【\]?=+]", text))
    if bad >= 2 and len(text) < 40:
        return True
    han = len(re.findall(r"[\u4e00-\u9fff]", text))
    if han > 0 and han / max(len(text), 1) < 0.4:
        return True
    return False


def postprocess_text(text: str) -> OcrPostprocessResult:
    fixes: list[OcrFixLog] = []
    t = text
    t = _apply_phrase_fixes(t, fixes)
    t = _fix_clause_3_1(t, fixes)
    t = _fix_key_width_b_vs_6(t, fixes)
    t = _fix_tolerance_plus_minus(t, fixes)
    t = _fix_dash_in_standard_no(t, fixes)
    t = _merge_split_411_line(t, fixes)
    t = _mark_clause_gaps(t, fixes)
    t = _insert_newlines_after_period(t, fixes)
    t = normalize_table_latex(t)

    gaps = detect_clause_gaps(t)
    low = _detect_garbled(t) or bool(gaps) or _GAP_TAG in t
    return OcrPostprocessResult(
        text=t, fixes=fixes, low_confidence=low, clause_gaps=gaps
    )


def append_fixes_log(all_fixes: list[OcrFixLog], log_path: Path) -> None:
    if not all_fixes:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        for fx in all_fixes:
            f.write(
                json.dumps(
                    {"rule": fx.rule, "before": fx.before, "after": fx.after},
                    ensure_ascii=False,
                )
                + "\n"
            )


def postprocess_content_list(items: list[dict]) -> tuple[list[dict], list[OcrFixLog]]:
    out: list[dict] = []
    all_fixes: list[OcrFixLog] = []
    for item in items:
        item = dict(item)
        if item.get("type") == "table":
            out.append(item)
            continue
        raw = (item.get("text") or "").strip()
        if not raw:
            item["ocr_empty"] = True
            item["confidence"] = "low"
            out.append(item)
            continue
        res = postprocess_text(raw)
        item["text"] = res.text
        item["ocr_fix_count"] = len(res.fixes)
        if res.clause_gaps:
            item["clause_gaps"] = res.clause_gaps
        if res.low_confidence:
            item["confidence"] = "low"
        elif res.fixes:
            item["confidence"] = "medium"
        all_fixes.extend(res.fixes)
        out.append(item)
    return out, all_fixes
