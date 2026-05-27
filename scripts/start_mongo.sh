#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/deploy/mongo"
docker compose up -d
echo "MongoDB: mongodb://localhost:27017 (db: pdf_agent)"
