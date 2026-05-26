#!/usr/bin/env bash
# 安装方案 B：Docling 解析后端（与 MinerU 互不覆盖，通过 .env 切换）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "请先创建虚拟环境: python3 -m venv .venv"
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -U pip
pip install -r requirements-docling.txt
echo ""
echo "Docling 已安装。在 .env 中设置："
echo "  PDF_PARSER_BACKEND=docling"
echo "  DOCLING_FORCE_REPARSE=true   # 首次或换 PDF 时"
echo "首次 Docling 会下载 HF 模型，请保证网络或设置 HF_ENDPOINT 镜像。"
echo "然后执行: python scripts/ingest.py"
