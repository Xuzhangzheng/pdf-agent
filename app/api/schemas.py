from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str | None = None


class SessionOut(BaseModel):
    id: str = Field(alias="_id")
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class MessageOut(BaseModel):
    id: str = Field(alias="_id")
    session_id: str
    role: str
    content: str
    created_at: datetime
    trace_id: str | None = None
    citations: list[Any] = []
    verification: dict[str, Any] = {}

    class Config:
        populate_by_name = True


class ChatRequest(BaseModel):
    question: str
