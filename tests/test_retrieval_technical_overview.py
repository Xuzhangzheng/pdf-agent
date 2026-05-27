"""技术条件总览题的检索钉住与英文块降权。"""
from __future__ import annotations

from src.agent.orchestrator import index_ready
from src.retrieval.query_signals import is_english_boilerplate_text
from src.retrieval.retriever import HybridRetriever


def test_retrieve_technical_overview_not_english_boilerplate():
    if not index_ready():
        return
    q = "技术条件具体包含着什么"
    out = HybridRetriever().retrieve(q, question_id="test-tech-overview")
    assert out.evidence, "expected evidence"
    texts = [e.text for e in out.evidence]
    assert not any(is_english_boilerplate_text(t) for t in texts), texts
    joined = "\n".join(texts)
    assert "技术要求" in joined or "3.1" in joined or "3.2" in joined, joined[:300]
    assert any(
        "除花键外的各种键的技术要求" in t or e.clause_id == "3.1"
        for e, t in zip(out.evidence, texts)
    )
