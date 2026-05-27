#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
# 使用 python -m uvicorn，避免 .venv/bin/uvicorn 仍指向旧路径（如 code/pdf-agent）的 shebang
exec .venv/bin/python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
