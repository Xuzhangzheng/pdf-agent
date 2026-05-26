from __future__ import annotations

import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, Field

ChunkType = Literal[
    "paragraph", "clause", "table", "figure_caption", "title", "appendix"
]
Confidence = Literal["high", "medium", "low"]


class Block(BaseModel):
    block_id: str
    chunk_type: ChunkType = "paragraph"
    page: int = 1
    text: str
    clause_id: Optional[str] = None
    clause_id_raw: Optional[str] = None
    table_id: Optional[str] = None
    section_title: Optional[str] = None
    parser: str = "mineru"
    confidence: Confidence = "high"


class Chunk(BaseModel):
    chunk_id: str
    block_id: str
    chunk_type: ChunkType
    page: int
    text: str
    clause_id: Optional[str] = None
    table_id: Optional[str] = None
    section_title: Optional[str] = None
    confidence: Confidence = "high"
    token_estimate: int = 0


class DocManifest(BaseModel):
    doc_id: str
    source_pdf: str
    page_count: int
    blocks: list[Block] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    quality: dict = Field(default_factory=dict)


def stable_id(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
