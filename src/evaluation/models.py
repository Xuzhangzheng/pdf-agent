from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CitationSpec(BaseModel):
    min_count: int = 1
    require_page: bool = True
    require_table_ref: bool = False


class RetrievalSpec(BaseModel):
    must_include_chunk_types: list[str] = Field(default_factory=list)
    min_hits: int = 1
    clause_id_pattern: Optional[str] = None


class AnswerGold(BaseModel):
    must_contain_any: list[str] = Field(default_factory=list)
    must_not_contain_any: list[str] = Field(default_factory=list)
    numeric_tolerance: Optional[float] = None


class LlmJudgeSpec(BaseModel):
    enabled: bool = True
    rubric: str = ""


class DemoQuestion(BaseModel):
    id: str
    question: str
    category: str
    expected_behavior: Literal["answer", "refuse"]
    must_refuse: bool = False
    citation: CitationSpec = Field(default_factory=CitationSpec)
    retrieval: RetrievalSpec = Field(default_factory=RetrievalSpec)
    answer_gold: AnswerGold = Field(default_factory=AnswerGold)
    llm_judge: LlmJudgeSpec = Field(default_factory=LlmJudgeSpec)
    regression_group: Optional[str] = None
    fuzzy_pair_id: Optional[str] = None
    fuzzy_clear_question: Optional[str] = None


class DemoQuestionBank(BaseModel):
    version: str = "1.0"
    questions: list[DemoQuestion]
