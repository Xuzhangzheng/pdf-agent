#!/usr/bin/env bash
# 在本机 Docker 启动 Langfuse v3 自托管栈
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LF_DIR="$ROOT/deploy/langfuse"

if ! command -v docker >/dev/null 2>&1; then
  echo "需要已安装 Docker。" >&2
  exit 1
fi

cd "$LF_DIR"
if [[ ! -f .env ]]; then
  cp .env.example .env
fi

# Langfuse 要求 ENCRYPTION_KEY / NEXTAUTH_SECRET 为 openssl rand -hex 32（64 个 hex 字符）
need_secrets=0
if ! grep -q '^ENCRYPTION_KEY=[0-9a-f]\{64\}$' .env 2>/dev/null; then
  need_secrets=1
fi
if ! grep -q '^NEXTAUTH_SECRET=[0-9a-f]\{64\}$' .env 2>/dev/null; then
  need_secrets=1
fi
if [[ "$need_secrets" -eq 1 ]]; then
  enc="$(openssl rand -hex 32)"
  sec="$(openssl rand -hex 32)"
  salt="$(openssl rand -hex 16)"
  if grep -q '^ENCRYPTION_KEY=' .env; then
    sed -i.bak "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${enc}|" .env
    sed -i.bak "s|^NEXTAUTH_SECRET=.*|NEXTAUTH_SECRET=${sec}|" .env
    sed -i.bak "s|^SALT=.*|SALT=${salt}|" .env
    rm -f .env.bak
  else
    printf '\nENCRYPTION_KEY=%s\nNEXTAUTH_SECRET=%s\nSALT=%s\n' "$enc" "$sec" "$salt" >> .env
  fi
  echo "已自动生成 ENCRYPTION_KEY / NEXTAUTH_SECRET / SALT（64 位 hex）。"
fi

docker compose pull
docker compose up -d

echo ""
echo "Langfuse UI: http://localhost:3000"
echo "首次启动若配置了 LANGFUSE_INIT_*，请登录后在 Settings → API Keys 复制到仓库根目录 .env："
echo "  LANGFUSE_HOST=http://localhost:3000"
echo "  LANGFUSE_PUBLIC_KEY=pk-lf-..."
echo "  LANGFUSE_SECRET_KEY=sk-lf-..."
echo ""
echo "查看日志: cd deploy/langfuse && docker compose logs -f langfuse-web"
