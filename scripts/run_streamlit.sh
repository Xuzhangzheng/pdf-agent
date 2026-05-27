#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ ! -x .venv/bin/streamlit ]]; then
  echo "请先安装环境: bash scripts/setup.sh" >&2
  exit 1
fi

exec .venv/bin/streamlit run app/streamlit_app.py --server.port "${STREAMLIT_PORT:-8501}"
