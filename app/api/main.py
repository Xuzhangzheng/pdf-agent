from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import chat, sessions

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="pdf-agent chat API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(sessions.router)
app.include_router(chat.router)

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/chat")
def chat_page():
    html = STATIC / "chat.html"
    if html.exists():
        return FileResponse(html)
    return {"message": "chat UI not found; use Streamlit 会话 Tab"}
