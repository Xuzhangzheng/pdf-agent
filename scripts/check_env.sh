#!/usr/bin/env bash
# 检查本机环境是否满足各档位运行需求
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

PROFILE="${1:-all}"
case "$PROFILE" in
  full) PROFILE="all" ;;
esac

export PYTHONPATH="$ROOT"
FAIL=0

warn() { echo "  [WARN] $*"; }
ok() { echo "  [OK]   $*"; }
fail() { echo "  [FAIL] $*"; FAIL=1; }

echo "pdf-agent 环境检查 (profile=${PROFILE})"
echo "项目目录: $ROOT"
echo ""

# --- Python / venv ---
echo "== Python"
if py="$(pdf_agent_find_python 3 10 2>/dev/null)"; then
  ok "系统 Python: $py ($($py --version 2>&1))"
else
  fail "未找到 Python 3.10+"
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  ok "虚拟环境: $ROOT/.venv ($("$ROOT/.venv/bin/python" --version 2>&1))"
else
  fail "虚拟环境不存在，请运行: bash scripts/setup.sh"
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY=""
fi

# --- pip 包 ---
echo ""
echo "== Python 依赖"
if [[ -n "$PY" ]]; then
  for mod in streamlit faiss httpx fastapi pymongo openai; do
    if "$PY" -c "import ${mod}" 2>/dev/null; then ok "import $mod"; else fail "缺少 $mod"; fi
  done
  if [[ "$PROFILE" == "all" ]]; then
    if [[ -x "$ROOT/.venv/bin/magic-pdf" ]] && "$ROOT/.venv/bin/magic-pdf" --help >/dev/null 2>&1; then
      ok "magic-pdf CLI"
    else
      fail "magic-pdf CLI 不可用，请: bash scripts/setup.sh"
    fi
    if "$PY" -c "from paddleocr import PPStructure" 2>/dev/null; then
      ok "paddleocr"
    else
      fail "paddleocr 未安装"
    fi
  fi
fi

# --- .env / API ---
echo ""
echo "== 配置"
if [[ -f "$ROOT/.env" ]]; then
  ok ".env 存在"
  if grep -q '^DASHSCOPE_API_KEY=.\+' "$ROOT/.env" 2>/dev/null; then ok "DASHSCOPE_API_KEY"; else fail "DASHSCOPE_API_KEY 未填写"; fi
  if grep -q '^ARK_API_KEY=.\+' "$ROOT/.env" 2>/dev/null; then ok "ARK_API_KEY"; else fail "ARK_API_KEY 未填写"; fi
else
  fail "缺少 .env，请: cp .env.example .env"
fi

# --- 索引 / 产物 ---
echo ""
echo "== 数据产物"
if [[ -n "$PY" ]] && "$PY" -c "from src.agent.orchestrator import index_ready; import sys; sys.exit(0 if index_ready() else 1)" 2>/dev/null; then
  ok "向量索引 index_meta.json"
else
  if [[ "$PROFILE" == "minimal" ]]; then
    warn "索引未就绪（minimal 档可自带 artifacts/faiss，或运行 ingest）"
  else
    fail "索引未就绪，请运行 ingest 或确认 artifacts/faiss 已提交"
  fi
fi
[[ -f "$ROOT/artifacts/parsed/doc.json" ]] && ok "artifacts/parsed/doc.json" || warn "无 doc.json（解析预览 Tab 为空）"

# --- Docker 服务 ---
echo ""
echo "== Docker 中间件"
if pdf_agent_docker_ready; then
  ok "Docker 运行中"
  if nc -z 127.0.0.1 27017 2>/dev/null; then ok "MongoDB :27017"; else
    if [[ "$PROFILE" == "all" ]]; then
      fail "MongoDB 未监听（请: bash scripts/setup.sh services）"
    else
      warn "MongoDB 未监听（会话 Tab: bash scripts/setup.sh services）"
    fi
  fi
  if curl -sf "http://127.0.0.1:3000/api/public/health" >/dev/null 2>&1 || curl -sf "http://127.0.0.1:3000" >/dev/null 2>&1; then
    ok "Langfuse :3000"
  else
    if [[ "$PROFILE" == "all" ]]; then
      warn "Langfuse 未就绪（请: bash scripts/setup.sh services，并在 UI 配置 API Keys）"
    else
      warn "Langfuse 未就绪（可选: bash scripts/setup.sh services）"
    fi
  fi
else
  if [[ "$PROFILE" == "all" ]]; then
    warn "Docker 不可用（会话 Tab / Langfuse 需 Docker；就绪后: bash scripts/setup.sh services）"
  else
    warn "Docker 不可用，跳过 MongoDB / Langfuse 检查"
  fi
fi

if curl -sf "http://127.0.0.1:8000/health" 2>/dev/null | grep -q '"ok"'; then
  ok "Chat API :8000"
else
  warn "Chat API 未启动（会话 Tab: bash scripts/run_api.sh）"
fi

echo ""
if [[ "$FAIL" -eq 0 ]]; then
  echo "检查通过。"
  exit 0
fi
echo "存在未通过项，详见上文。安装指引: docs/setup/environment.md"
exit 1
