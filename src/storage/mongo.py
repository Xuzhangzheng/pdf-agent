"""MongoDB persistence for chat sessions and messages."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from src.config.settings import Settings, get_settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client: MongoClient | None = None

    @property
    def client(self) -> MongoClient:
        if self._client is None:
            self._client = MongoClient(
                self.settings.mongodb_uri,
                serverSelectionTimeoutMS=5000,
            )
        return self._client

    @property
    def db(self) -> Database:
        return self.client[self.settings.mongodb_db]

    @property
    def sessions(self) -> Collection:
        return self.db.chat_sessions

    @property
    def messages(self) -> Collection:
        return self.db.chat_messages

    def ensure_indexes(self) -> None:
        self.messages.create_index(
            [("session_id", ASCENDING), ("created_at", ASCENDING)]
        )

    def create_session(self, title: str | None = None) -> dict[str, Any]:
        now = _utcnow()
        doc = {
            "_id": str(uuid4()),
            "title": title or "新会话",
            "created_at": now,
            "updated_at": now,
            "metadata": {},
        }
        self.sessions.insert_one(doc)
        return doc

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self.sessions.find().sort("updated_at", -1).limit(limit)
        return list(cur)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self.sessions.find_one({"_id": session_id})

    def touch_session(self, session_id: str) -> None:
        self.sessions.update_one(
            {"_id": session_id},
            {"$set": {"updated_at": _utcnow()}},
        )

    def add_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        trace_id: str | None = None,
        citations: list | None = None,
        verification: dict | None = None,
        status: str = "completed",
    ) -> dict[str, Any]:
        now = _utcnow()
        doc = {
            "_id": str(uuid4()),
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": now,
            "trace_id": trace_id,
            "citations": citations or [],
            "verification": verification or {},
            "status": status,
        }
        self.messages.insert_one(doc)
        self.touch_session(session_id)
        return doc

    def list_messages(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        cur = (
            self.messages.find({"session_id": session_id})
            .sort("created_at", ASCENDING)
            .limit(limit)
        )
        return list(cur)

    def recent_turns(self, session_id: str, n: int = 5) -> list[dict[str, Any]]:
        cur = (
            self.messages.find({"session_id": session_id})
            .sort("created_at", -1)
            .limit(n * 2)
        )
        rows = list(cur)
        rows.reverse()
        return rows


_store: ChatStore | None = None


def get_chat_store() -> ChatStore:
    global _store
    if _store is None:
        _store = ChatStore()
        _store.ensure_indexes()
    return _store
