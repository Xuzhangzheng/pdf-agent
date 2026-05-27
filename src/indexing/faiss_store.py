from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

# macOS：避免 faiss 触发 numpy Accelerate 自检导致 segfault（见 numpy _mac_os_check）
if sys.platform == "darwin":
    os.environ.setdefault("NPY_DISABLE_MACOS_ACCELERATE", "1")

import faiss
import numpy as np

logger = logging.getLogger(__name__)

INDEX_FILENAME = "index.faiss"
STORE_FILENAME = "store.json"


class FaissVectorStore:
    """本地 FAISS 稠密索引（IndexFlatIP + L2 归一化，等价 cosine）。"""

    def __init__(
        self,
        *,
        index: faiss.Index,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ):
        self._index = index
        self._ids = ids
        self._documents = documents
        self._metadatas = metadatas

    @property
    def index_dir(self) -> Path | None:
        return getattr(self, "_index_dir", None)

    def count(self) -> int:
        return self._index.ntotal

    @classmethod
    def build(
        cls,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        index_dir: Path,
    ) -> FaissVectorStore:
        if not (len(ids) == len(embeddings) == len(documents) == len(metadatas)):
            raise ValueError("ids, embeddings, documents, metadatas length mismatch")
        if not ids:
            raise ValueError("cannot build empty FAISS index")

        index_dir = Path(index_dir)
        if index_dir.exists():
            shutil.rmtree(index_dir)
        index_dir.mkdir(parents=True, exist_ok=True)

        matrix = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(matrix)
        dim = matrix.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(matrix)

        faiss.write_index(index, str(index_dir / INDEX_FILENAME))
        (index_dir / STORE_FILENAME).write_text(
            json.dumps(
                {"ids": ids, "documents": documents, "metadatas": metadatas},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info("FAISS index built: %d vectors, dim=%d", len(ids), dim)
        store = cls(index=index, ids=ids, documents=documents, metadatas=metadatas)
        store._index_dir = index_dir
        return store

    @classmethod
    def load(cls, index_dir: Path) -> FaissVectorStore:
        index_dir = Path(index_dir)
        index_path = index_dir / INDEX_FILENAME
        store_path = index_dir / STORE_FILENAME
        if not index_path.is_file() or not store_path.is_file():
            raise FileNotFoundError(
                f"FAISS index not found under {index_dir}. Run ingest."
            )
        index = faiss.read_index(str(index_path))
        payload = json.loads(store_path.read_text(encoding="utf-8"))
        store = cls(
            index=index,
            ids=list(payload["ids"]),
            documents=list(payload["documents"]),
            metadatas=list(payload["metadatas"]),
        )
        store._index_dir = index_dir
        if index.ntotal != len(store._ids):
            raise ValueError(
                f"FAISS index row count {index.ntotal} != store ids {len(store._ids)}"
            )
        return store

    def search(
        self,
        query_embedding: list[float],
        k: int,
    ) -> tuple[list[str], list[dict[str, Any]], list[float]]:
        if self._index.ntotal == 0:
            return [], [], []
        k = min(max(k, 1), self._index.ntotal)
        q = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(q)
        similarities, indices = self._index.search(q, k)
        row_ids: list[str] = []
        metas: list[dict[str, Any]] = []
        distances: list[float] = []
        for sim, idx in zip(similarities[0], indices[0]):
            if idx < 0:
                continue
            i = int(idx)
            row_ids.append(self._ids[i])
            metas.append(self._metadatas[i])
            distances.append(max(0.0, 1.0 - float(sim)))
        return row_ids, metas, distances
