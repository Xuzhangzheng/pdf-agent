#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

bash scripts/fix_mineru_env.sh

cp -n .env.example .env 2>/dev/null || true
echo "Done. 编辑 .env 填写 DASHSCOPE_API_KEY 与 ARK_API_KEY，然后运行 run_mineru_poc.py / ingest.py"
