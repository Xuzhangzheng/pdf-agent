#!/usr/bin/env bash
# 修复 MinerU/Paddle 与 NumPy 2.x 冲突（macOS 常见）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "请先创建虚拟环境: python3 -m venv .venv"
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> 1/6 卸载会拉高 NumPy 2.x 的 OpenCV"
pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python 2>/dev/null || true

echo "==> 2/6 锁定 NumPy 1.26.x"
pip install -U pip
pip install "numpy==1.26.4" --force-reinstall

echo "==> 3/6 安装与 Paddle 匹配的 OpenCV（不拉取依赖，避免升级 NumPy）"
pip install "opencv-python-headless==4.6.0.66" --no-deps --force-reinstall

echo "==> 4/6 安装项目基础依赖（保持 numpy 1.x）"
pip install -r requirements.txt
pip install "numpy==1.26.4" --force-reinstall

echo "==> 5/6 安装 MinerU CPU（macOS ARM 通常无法装 detectron2，full 会自动回退 lite）"
pip install "magic-pdf[cpu]>=0.6.0"
pip install "numpy==1.26.4" --force-reinstall
pip install "opencv-python-headless==4.6.0.66" --no-deps --force-reinstall
# Linux x86_64 若需 full：pip install "magic-pdf[full-cpu]" detectron2 --extra-index-url https://myhloli.github.io/wheels/

echo "==> 6/6 验证"
python - <<'PY'
import numpy as np
assert np.__version__.startswith("1."), f"numpy must be 1.x, got {np.__version__}"
print("numpy", np.__version__)
import cv2
print("cv2", cv2.__version__)
from paddleocr import PPStructure
print("paddleocr OK")
PY

if [[ ! -f "$HOME/magic-pdf.json" ]]; then
  python3 - <<'PY'
import json
from pathlib import Path
root = Path(".").resolve()
cfg = json.loads((root / "config/magic-pdf.json").read_text())
for k in ("temp-output-dir", "models-dir"):
    p = Path(cfg[k])
    if not p.is_absolute():
        cfg[k] = str((root / p).resolve())
Path.home().joinpath("magic-pdf.json").write_text(json.dumps(cfg, indent=2))
print("已创建 ~/magic-pdf.json")
PY
fi

echo ""
echo "环境修复完成。请执行："
echo "  python scripts/run_mineru_poc.py"
echo "  python scripts/ingest.py"
