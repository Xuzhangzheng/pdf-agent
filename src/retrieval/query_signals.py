from __future__ import annotations

import re

# 4.l.2 → 4.1.2（l 误识为 1）
_OCR_DOT_L_RE = re.compile(
    r"(\d+)\.([lI\|])\.(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
_OCR_CLAUSE_RE = re.compile(
    r"(\d+)[lI\|](\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
_CLAUSE_RE = re.compile(r"\b(\d+(?:\.\d+)+)\b")
_TABLE_NUM_RE = re.compile(r"表\s*(\d+)", re.IGNORECASE)

# 勿单独用「公差」——会误伤「形位公差」类条款题
_TABLE_INTENT_KW = (
    "表",
    "表格",
    "尺寸",
    "参数",
    "限值",
    "aql",
    "键宽",
    "键高",
    "键长",
)

_APPEARANCE_KW = ("表面", "外观", "粗糙", "裂纹", "浮锈", "毛刺", "氧化皮")


def normalize_clause_token(raw: str) -> str:
    s = raw.strip().translate(str.maketrans({"l": "1", "I": "1", "|": "1", "O": "0"}))
    m = _OCR_DOT_L_RE.search(s)
    if m:
        return f"{m.group(1)}.1.{m.group(3)}"
    m = _OCR_CLAUSE_RE.search(s)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return s


def extract_clause_ids_from_query(query: str) -> list[str]:
    found: list[str] = []
    for m in _OCR_DOT_L_RE.finditer(query):
        cid = f"{m.group(1)}.1.{m.group(3)}"
        if cid not in found:
            found.append(cid)
    for m in _OCR_CLAUSE_RE.finditer(query):
        cid = f"{m.group(1)}.{m.group(2)}"
        if cid not in found:
            found.append(cid)
    for m in _CLAUSE_RE.finditer(query):
        cid = normalize_clause_token(m.group(1))
        if cid and cid not in found and len(cid) <= 12:
            found.append(cid)
    return found


def extract_table_id_from_query(query: str) -> str | None:
    m = _TABLE_NUM_RE.search(query)
    if m:
        return f"表{m.group(1)}"
    return None


def wants_table_evidence(query: str) -> bool:
    if _TABLE_NUM_RE.search(query) or "表格" in query:
        return True
    return any(k in query for k in _TABLE_INTENT_KW)


def wants_appearance_clauses(query: str) -> bool:
    return any(k in query for k in _APPEARANCE_KW)


_COMPOSITE_KW = ("抗拉强度", "材料", "热处理", "硬度", "表1", "检查项目")


_SCOPE_KW = (
    "范围",
    "适用于",
    "规定什么",
    "管啥的",
    "管啥",
    "哪些类型",
    "讲什么",
    "说什么",
    "讲的是什么",
    "什么内容",
)

_TECH_REQUIREMENTS_OVERVIEW_KW = (
    "技术条件",
    "包含着",
    "包含什么",
    "包含哪些",
    "有哪些内容",
    "包括什么",
    "包括哪些",
    "具体包含",
    "都包含",
    "有哪些规定",
    "有哪些要求",
)


def wants_scope_answer(query: str) -> bool:
    return any(k in query for k in _SCOPE_KW)


def wants_technical_requirements_overview(query: str) -> bool:
    """问标准/技术条件整体包含哪些内容（范围 + 第3章等）。"""
    if wants_scope_answer(query):
        return True
    return any(k in query for k in _TECH_REQUIREMENTS_OVERVIEW_KW)


def is_english_boilerplate_text(text: str) -> bool:
    """MinerU 页眉英文标题等，对中文问答无证据价值。"""
    t = (text or "").strip()
    if not t or len(t) > 160:
        return False
    chinese = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
    if chinese >= 10:
        return False
    lower = t.lower()
    if "technical specification" in lower and "key" in lower:
        return True
    return chinese == 0 and len(t) < 100 and t.isascii()


def wants_composite_strength_table(query: str) -> bool:
    return "抗拉强度" in query and ("表" in query or "检查" in query)


def wants_inspection_topics(query: str) -> bool:
    return any(k in query for k in ("检验", "验收", "抽样", "合格质量"))


# 第 3 章「技术要求」常用条款（技术条件总览题检索钉住）
TECH_REQUIREMENTS_CLAUSE_IDS = ("3.1", "3.2", "3.3", "3.4", "3.5", "3.6")
