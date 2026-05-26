from __future__ import annotations

from types import SimpleNamespace

from scripts.evaluate import _check_citations


def test_citation_requires_table_ref():
    spec = SimpleNamespace(min_count=1, require_page=True, require_table_ref=True)
    state = {
        "final_answer": "键宽 1.0 mm [p.4 表1]",
        "citations": [{"page": 4, "table_id": "表1"}],
    }
    assert _check_citations(state, spec) is True


def test_citation_table_from_answer_text():
    spec = SimpleNamespace(min_count=1, require_page=True, require_table_ref=True)
    state = {
        "final_answer": "见表1 [p.4]",
        "citations": [{"page": 4}],
    }
    assert _check_citations(state, spec) is True
