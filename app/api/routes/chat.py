from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest
from src.agent.stream_query import stream_ask
from src.storage.mongo import get_chat_store

router = APIRouter(prefix="/api/sessions", tags=["chat"])


@router.post("/{session_id}/chat")
def chat_sse(session_id: str, body: ChatRequest):
    store = get_chat_store()
    if not store.get_session(session_id):
        raise HTTPException(404, "session not found")

    history = store.recent_turns(session_id)

    def event_gen():
        final: dict | None = None
        for frame in stream_ask(
            body.question,
            chat_session_id=session_id,
            history=history,
        ):
            if frame.startswith("event: done"):
                import json

                for line in frame.split("\n"):
                    if line.startswith("data: "):
                        final = json.loads(line[6:])
                        break
            yield frame

        if final:
            store.add_message(
                session_id=session_id,
                role="user",
                content=body.question,
            )
            store.add_message(
                session_id=session_id,
                role="assistant",
                content=final.get("answer", ""),
                trace_id=final.get("trace_id"),
                citations=final.get("citations"),
                verification=final.get("verification"),
            )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
