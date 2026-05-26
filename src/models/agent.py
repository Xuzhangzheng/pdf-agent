from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class Citation(BaseModel):
    page: int
    snippet: str
    clause_id: Optional[str] = None
    table_id: Optional[str] = None
    chunk_id: Optional[str] = None


class Evidence(BaseModel):
    chunk_id: str
    text: str
    page: int
    chunk_type: str
    clause_id: Optional[str] = None
    table_id: Optional[str] = None
    rrf_score: float = 0.0
    bm25_score: float = 0.0
    rerank_score: Optional[float] = None


class ReflectionResult(BaseModel):
    has_evidence: bool = True
    hallucination_risk: Literal["low", "medium", "high"] = "low"
    should_refuse: bool = False
    unsupported_claims: List[str] = Field(default_factory=list)
    missing_citations: List[str] = Field(default_factory=list)
    critique: str = ""
    action: Literal["accept", "revise", "re_retrieve", "refuse"] = "accept"


class VerificationResult(BaseModel):
    has_evidence: bool = False
    hallucination_risk: str = "low"
    should_refuse: bool = False
    unsupported_claims: List[str] = Field(default_factory=list)
    reflection_rounds: int = 0
    re_retrieve_count: int = 0
    retrieval_round: int = 0
    reranker_degraded: Union[str, bool] = False


class AgentState(TypedDict, total=False):
    question: str
    question_id: Optional[str]
    rewritten_query: Optional[str]
    evidence: List[Dict[str, Any]]
    draft_answer: str
    final_answer: str
    citations: List[Dict[str, Any]]
    reflection_notes: List[Dict[str, Any]]
    reflection_count: int
    re_retrieve_count: int
    retrieval_round: int
    verification: Dict[str, Any]
    hard_refused: bool
    reranker_degraded: Union[str, bool]
    session_id: Optional[str]
    _last_reflection: Dict[str, Any]
    error: Optional[str]
