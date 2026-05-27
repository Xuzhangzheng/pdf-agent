"""Normalize LaTeX table artifacts (e.g. \\multicolumn) in OCR Markdown."""
from __future__ import annotations

import re

# \multicolumn{3}{c}{1.0} or broken \multicolumn{3}{c\t}{1.0}
_MULTICOLUMN_VALUE_RE = re.compile(
    r"\\multicolumn\s*\{[^}]*\}\s*\{[^}]*\}\s*\{([^}]*)\}",
    re.IGNORECASE,
)
# Orphan fragments: \multicolumn{3}{c without closing brace value
_MULTICOLUMN_ORPHAN_RE = re.compile(
    r"\\multicolumn\s*\{[^}]*\}\s*\{[^}]*\}\s*",
    re.IGNORECASE,
)
# Lone \multicolumn{3}{c (no value brace)
_MULTICOLUMN_STUB_RE = re.compile(
    r"\\multicolumn\s*\{[^}]*\}\s*\{[^}]*\}",
    re.IGNORECASE,
)


def normalize_table_latex(text: str) -> str:
    if not text or "\\multicolumn" not in text:
        return text

    def _repl(m: re.Match) -> str:
        val = (m.group(1) or "").strip()
        return val if val and val != "—" else "—"

    out = _MULTICOLUMN_VALUE_RE.sub(_repl, text)
    out = _MULTICOLUMN_ORPHAN_RE.sub("", out)
    out = _MULTICOLUMN_STUB_RE.sub("", out)
    # Collapse pipe cells that became empty spacing
    out = re.sub(r"\|\s*\|\s*", "| — |", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out
