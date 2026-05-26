from __future__ import annotations

from src.config.settings import Settings
from src.models.agent import Evidence
from src.models.blocks import Chunk
from src.retrieval.retriever import HybridRetriever


def _table_chunk() -> Chunk:
    return Chunk(
        chunk_id="t1",
        block_id="b1",
        chunk_type="table",
        page=4,
        text="| 键宽 | 1.0 |",
        table_id="表1",
    )


def _clause_chunk(cid: str = "4.1.2") -> Chunk:
    return Chunk(
        chunk_id=f"c_{cid}",
        block_id="b2",
        chunk_type="clause",
        page=4,
        text=f"{cid} 供方检验。",
        clause_id=cid,
    )


def test_pin_table_after_rerank():
    r = HybridRetriever(Settings())
    chunks = [_table_chunk(), _clause_chunk("3.1")]
    ev = [
        Evidence(
            chunk_id="c_3.1",
            text="3.1",
            page=3,
            chunk_type="clause",
            clause_id="3.1",
        )
    ]
    q = "请根据标准中的表格说明键的尺寸、公差或相关参数限值。"
    out = r._pin_required_after_rerank(ev, chunks, q, top_n=5)
    assert any(e.chunk_type == "table" for e in out)
    assert out[0].chunk_type == "table"


def test_pin_clause_after_rerank():
    r = HybridRetriever(Settings())
    chunks = [_clause_chunk("4.1.2"), _table_chunk()]
    ev = [
        Evidence(
            chunk_id="t1",
            text="table",
            page=4,
            chunk_type="table",
            table_id="表1",
        )
    ]
    q = "条款 4.l.2 对键的形位公差有何要求？"
    out = r._pin_required_after_rerank(ev, chunks, q, top_n=5)
    assert any(e.clause_id == "4.1.2" for e in out)


def test_pin_appearance_clauses():
    r = HybridRetriever(Settings())
    chunks = [
        Chunk(
            chunk_id="c32",
            block_id="b",
            chunk_type="clause",
            page=3,
            text="3.2 裂纹",
            clause_id="3.2",
        ),
        Chunk(
            chunk_id="c33",
            block_id="b",
            chunk_type="clause",
            page=3,
            text="3.3 粗糙度",
            clause_id="3.3",
        ),
    ]
    ev: list[Evidence] = []
    q = "键的技术要求中，对表面粗糙度或外观质量有哪些规定？"
    out = r._pin_required_after_rerank(ev, chunks, q, top_n=5)
    cids = {e.clause_id for e in out}
    assert "3.2" in cids and "3.3" in cids


def test_ensure_required_injects_table():
    r = HybridRetriever(Settings())
    chunks = [_table_chunk(), _clause_chunk("3.5")]
    ev: list[Evidence] = []
    q = "表格中键高的限值是多少？"
    out = r._ensure_required_chunks(ev, chunks, q, top_n=5)
    assert any(e.chunk_type == "table" for e in out)
