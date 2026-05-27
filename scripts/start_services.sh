#!/usr/bin/env bash
# 启动 Docker 依赖服务：MongoDB、Langfuse（需 Docker 已安装并运行）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
pdf_agent_require_docker

TARGET="${1:-all}"

pdf_agent_run_docker_services "$ROOT" "$TARGET"

echo ""
echo "服务启动请求已发送。验证: bash scripts/check_env.sh all"
