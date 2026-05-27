#!/usr/bin/env bash
# 兼容旧文档：等价于无参 setup.sh（完整 Python + 尝试 Docker）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "$ROOT/scripts/setup.sh" "$@"
