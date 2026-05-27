from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import MessageOut, SessionCreate, SessionOut
from src.storage.mongo import get_chat_store

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _session_out(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "title": doc.get("title", ""),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def _message_out(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "session_id": doc["session_id"],
        "role": doc["role"],
        "content": doc["content"],
        "created_at": doc.get("created_at"),
        "trace_id": doc.get("trace_id"),
        "citations": doc.get("citations") or [],
        "verification": doc.get("verification") or {},
    }


@router.post("")
def create_session(body: SessionCreate):
    doc = get_chat_store().create_session(title=body.title)
    return _session_out(doc)


@router.get("")
def list_sessions():
    docs = get_chat_store().list_sessions()
    return [_session_out(d) for d in docs]


@router.get("/{session_id}/messages")
def list_messages(session_id: str):
    store = get_chat_store()
    if not store.get_session(session_id):
        raise HTTPException(404, "session not found")
    docs = store.list_messages(session_id)
    return [_message_out(d) for d in docs]
