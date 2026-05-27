from __future__ import annotations

"""FAISS 双稠密索引：正文 + 预设问题向量，检索时归并到 chunk_id。"""

INDEX_ROLE_CONTENT = "content"
INDEX_ROLE_QUESTION = "question"


def dense_row_id_for_question(chunk_id: str, index: int) -> str:
    return f"{chunk_id}#q{index}"


def resolve_chunk_id(row_id: str, metadata: dict | None) -> str:
    if metadata and metadata.get("chunk_id"):
        return str(metadata["chunk_id"])
    if "#q" in row_id:
        return row_id.split("#q", 1)[0]
    return row_id


def best_dense_ranks_per_chunk(
    row_ids: list[str],
    metadatas: list[dict],
) -> dict[str, int]:
    """同一 chunk 的正文/多问句命中取最优（最小）名次。"""
    ranks: dict[str, int] = {}
    for rank, (rid, meta) in enumerate(zip(row_ids, metadatas), start=1):
        chunk_id = resolve_chunk_id(rid, meta)
        if chunk_id not in ranks or rank < ranks[chunk_id]:
            ranks[chunk_id] = rank
    return ranks


def best_dense_scores_per_chunk(
    row_ids: list[str],
    metadatas: list[dict],
    dist_by_id: dict[str, float],
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for rid, meta in zip(row_ids, metadatas):
        chunk_id = resolve_chunk_id(rid, meta)
        d = dist_by_id.get(rid, 1.0)
        s = 1.0 / (1.0 + d)
        if chunk_id not in scores or s > scores[chunk_id]:
            scores[chunk_id] = s
    return scores
