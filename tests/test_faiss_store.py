import numpy as np

from src.indexing.dual_dense import (
    best_dense_scores_per_chunk,
    dense_row_id_for_question,
    resolve_chunk_id,
)
from src.indexing.faiss_store import FaissVectorStore


def _unit(v: list[float]) -> list[float]:
    a = np.array(v, dtype=np.float32)
    a /= np.linalg.norm(a) + 1e-12
    return a.tolist()


def test_faiss_build_search_and_merge(tmp_path):
    ids = ["c1", dense_row_id_for_question("c1", 0), "c2"]
    embeddings = [_unit([1.0, 0.0, 0.0]), _unit([0.99, 0.1, 0.0]), _unit([0.0, 1.0, 0.0])]
    documents = ["正文 c1", "问句 c1", "正文 c2"]
    metadatas = [
        {"chunk_id": "c1", "index_role": "content"},
        {"chunk_id": "c1", "index_role": "question"},
        {"chunk_id": "c2", "index_role": "content"},
    ]

    FaissVectorStore.build(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
        index_dir=tmp_path,
    )
    store = FaissVectorStore.load(tmp_path)
    assert store.count() == 3

    q = _unit([1.0, 0.0, 0.0])
    row_ids, metas, dists = store.search(q, k=3)
    assert len(row_ids) == 3
    assert all(0.0 <= d <= 1.0 for d in dists)
    assert dists[0] <= dists[-1]

    dist_by_id = dict(zip(row_ids, dists))
    scores = best_dense_scores_per_chunk(row_ids, metas, dist_by_id)
    assert "c1" in scores
    assert resolve_chunk_id(row_ids[0], metas[0]) == "c1"
