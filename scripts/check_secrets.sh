#!/usr/bin/env bash
# 提交前扫描：检测将被 Git 跟踪的文件中是否含疑似 API Key
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not a git repo yet; scanning tracked-eligible files via git ls-files (after init) or find."
  FILES=$(find . -type f \
    ! -path './.venv/*' \
    ! -path './artifacts/*' \
    ! -path './.git/*' \
    ! -path './.agents/*' \
    ! -path './.pytest_cache/*' \
    ! -name '.env' \
    \( -name '*.py' -o -name '*.md' -o -name '*.json' -o -name '*.sh' -o -name '*.toml' -o -name '.env.example' \) 2>/dev/null || true)
else
  FILES=$(git ls-files)
fi

PATTERNS=(
  'sk-[a-zA-Z0-9]{20,}'
  'DASHSCOPE_API_KEY=sk-'
  'ARK_API_KEY=[0-9a-f]{8}-[0-9a-f]{4}-'
)

FOUND=0
for pat in "${PATTERNS[@]}"; do
  if echo "$FILES" | xargs grep -lE "$pat" 2>/dev/null | grep -v '^\.env$' | grep -v 'check_secrets.sh' | grep -q .; then
    echo "ERROR: Pattern matched: $pat"
    echo "$FILES" | xargs grep -nE "$pat" 2>/dev/null | grep -v '^\.env:' | grep -v 'check_secrets.sh' || true
    FOUND=1
  fi
done

if [[ "$FOUND" -ne 0 ]]; then
  echo "Secret scan FAILED. Remove keys before commit."
  exit 1
fi

echo "Secret scan OK (no API keys in files to be committed)."
