#!/usr/bin/env bash
# 一键安装 pdf-agent 运行环境
# 用法:
#   bash scripts/setup.sh              # 默认：完整 Python + 尝试 Docker（推荐换机）
#   bash scripts/setup.sh --no-docker  # 完整 Python，不启动 Docker
#   bash scripts/setup.sh minimal      # 仅 RAG（已有 artifacts）
#   bash scripts/setup.sh services     # 仅 MongoDB + Langfuse（需 Docker）
#   bash scripts/setup.sh standard     # 兼容别名：等同 minimal（已移除 Docling）
#   bash scripts/setup.sh full         # 兼容：等同默认 Python 部分（不含 Docker）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

PROFILE="all"
NO_DOCKER=0
POSITIONAL=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-docker) NO_DOCKER=1; shift ;;
    --docker)
      echo "提示: --docker 已合并到默认行为，无需再指定。" >&2
      shift
      ;;
    -h|--help)
      sed -n '2,11p' "$0"
      exit 0
      ;;
    -*)
      echo "未知参数: $1" >&2
      exit 1
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done

if [[ ${#POSITIONAL[@]} -gt 0 ]]; then
  PROFILE="${POSITIONAL[0]}"
fi

# 兼容别名
case "$PROFILE" in
  full) PROFILE="all" ;;
  docker) PROFILE="services" ;;
  standard)
    echo "提示: standard 档已弃用（已移除 Docling），按 minimal 安装。" >&2
    PROFILE="minimal"
    ;;
esac

case "$PROFILE" in
  all|minimal|services) ;;
  *)
    echo "用法: bash scripts/setup.sh [all|minimal|services] [--no-docker]" >&2
    echo "  无参数 = all（requirements + MinerU + 尝试 Docker）" >&2
    exit 1
    ;;
esac

if [[ "$PROFILE" == "services" ]]; then
  echo "========================================"
  echo " pdf-agent Docker 中间件 (MongoDB + Langfuse)"
  echo "========================================"
  pdf_agent_require_docker
  pdf_agent_run_docker_services "$ROOT" all
  echo ""
  echo "中间件已启动。验证: bash scripts/check_env.sh all"
  exit 0
fi

echo "========================================"
echo " pdf-agent 环境安装  profile=${PROFILE}"
echo "========================================"

pdf_agent_ensure_venv "$ROOT"
export PYTHONPATH="$ROOT"

echo "==> 安装基础依赖 (requirements.txt)"
pip install -U pip
pip install -r requirements.txt

if [[ "$PROFILE" == "all" ]]; then
  echo "==> 安装 MinerU / Paddle (scripts/fix_mineru_env.sh)"
  bash "$ROOT/scripts/fix_mineru_env.sh"
fi

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "==> 已创建 .env，请填写 DASHSCOPE_API_KEY 与 ARK_API_KEY"
else
  echo "==> 保留已有 .env"
fi

if [[ "$PROFILE" == "all" && "$NO_DOCKER" -eq 0 ]]; then
  pdf_agent_try_start_docker_services "$ROOT" all || true
fi

CHECK_PROFILE="$PROFILE"
[[ "$PROFILE" == "all" ]] && CHECK_PROFILE="all"

echo ""
echo "安装完成 (profile=${PROFILE})。"
echo "  检查环境: bash scripts/check_env.sh ${CHECK_PROFILE}"
echo "  详细说明: docs/setup/environment.md"
echo ""
case "$PROFILE" in
  minimal)
    echo "下一步:"
    echo "  bash scripts/run_streamlit.sh"
    echo "  .venv/bin/python scripts/evaluate.py"
    ;;
  all)
    echo "下一步:"
    echo "  bash scripts/check_env.sh all"
    echo "  .venv/bin/python scripts/ingest.py --force-full   # 可选：重建索引"
    echo "  bash scripts/run_api.sh          # 另开终端 · 会话 Tab"
    echo "  bash scripts/run_streamlit.sh"
    ;;
esac
