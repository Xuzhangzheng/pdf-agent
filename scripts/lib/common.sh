# shellcheck shell=bash
# 供 scripts/*.sh source 的公共函数

pdf_agent_root() {
  echo "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
}

pdf_agent_docker_ready() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

pdf_agent_require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "错误：未找到 docker 命令。请先安装 Docker Desktop。" >&2
    return 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "错误：Docker 未运行。请启动 Docker Desktop 后重试。" >&2
    return 1
  fi
}

pdf_agent_run_docker_services() {
  local root="$1"
  local target="${2:-all}"
  case "$target" in
    mongo) bash "$root/scripts/start_mongo.sh" ;;
    langfuse) bash "$root/scripts/start_langfuse.sh" ;;
    all)
      bash "$root/scripts/start_mongo.sh"
      bash "$root/scripts/start_langfuse.sh"
      ;;
    *)
      echo "未知 Docker 服务目标: $target" >&2
      return 1
      ;;
  esac
}

# 供 setup.sh 默认流程调用：Docker 不可用时仅提示，不中断 Python 安装
pdf_agent_try_start_docker_services() {
  local root="$1"
  local target="${2:-all}"
  if pdf_agent_docker_ready; then
    echo "==> 启动 Docker 中间件 (${target})"
    pdf_agent_run_docker_services "$root" "$target"
    return 0
  fi
  echo ""
  echo "[跳过] Docker 未安装或未启动，MongoDB / Langfuse 未启动。"
  echo "如需仅启动中间件，请先安装并启动 Docker Desktop，再执行："
  echo "  bash scripts/setup.sh services"
  echo ""
  return 1
}

pdf_agent_find_python() {
  local min_major="${1:-3}"
  local min_minor="${2:-10}"
  local py
  for py in python3.12 python3.11 python3.10 python3; do
    if command -v "$py" >/dev/null 2>&1; then
      if "$py" -c "import sys; raise SystemExit(0 if sys.version_info >= (${min_major}, ${min_minor}) else 1)" 2>/dev/null; then
        echo "$py"
        return 0
      fi
    fi
  done
  return 1
}

pdf_agent_activate_venv() {
  local root="$1"
  # shellcheck disable=SC1091
  source "$root/.venv/bin/activate"
}

pdf_agent_ensure_venv() {
  local root="$1"
  local py
  py="$(pdf_agent_find_python 3 10)" || {
    echo "错误：需要 Python 3.10 或更高版本（推荐 3.10 / 3.11）。" >&2
    echo "  macOS: brew install python@3.11" >&2
    return 1
  }
  if [[ ! -d "$root/.venv" ]]; then
    echo "==> 创建虚拟环境 ($py)"
    "$py" -m venv "$root/.venv"
  fi
  pdf_agent_activate_venv "$root"
  local ver
  ver="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  echo "==> 使用 Python $ver ($root/.venv)"
}
