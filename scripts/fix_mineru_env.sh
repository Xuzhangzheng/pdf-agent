#!/usr/bin/env bash
# MinerU (magic-pdf) + PaddleOCR；锁定 NumPy 1.x，避免与 Paddle/Docling 冲突
# 要求：Python 3.10+（magic-pdf 1.3+ 使用 3.10 类型语法）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "请先创建虚拟环境: bash scripts/setup.sh" >&2
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "错误: MinerU 需要 Python 3.10+，当前: $(python --version)" >&2
  echo "请删除 .venv 后执行: bash scripts/setup.sh" >&2
  exit 1
}

pin_mineru_runtime() {
  # 避免 pip 依赖解析把 numpy 升到 2.x、transformers 升到 4.56+（公式识别会静默失败）
  pip uninstall -y opencv-python opencv-contrib-python 2>/dev/null || true
  pip install -r requirements-mineru.txt --no-deps --force-reinstall
  pip install "pycocotools>=2.0.6"
}

echo "==> 1/7 准备 pip / 卸载冲突 OpenCV"
pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python 2>/dev/null || true
pip install -U pip

echo "==> 2/7 安装项目基础依赖"
pip install -r requirements.txt
pin_mineru_runtime

echo "==> 3/7 安装 magic-pdf（含 full 依赖）"
# 1.3.x CLI: magic-pdf -p PDF -o OUT -m ocr
if [[ "$(uname -s)" == "Darwin" ]]; then
  pip install "magic-pdf[full_old_linux]>=1.2.0"
else
  pip install "magic-pdf[full]>=1.2.0"
fi
pin_mineru_runtime

echo "==> 4/7 安装 PaddlePaddle + PaddleOCR"
if ! pip install "paddlepaddle==2.6.2" 2>/dev/null; then
  echo "    尝试 Paddle 官方源..."
  pip install paddlepaddle==2.6.2 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
fi
pip install "paddleocr>=2.7,<3.0" --no-deps
pip install shapely pyclipper lmdb tqdm Pillow pyyaml python-dateutil attrdict fire
pin_mineru_runtime

echo "==> 5/7 下载 MinerU 模型（若尚未存在 yolo_v8_ft.pt）"
MARKER="$ROOT/artifacts/mineru/models/MFD/YOLO/yolo_v8_ft.pt"
if [[ ! -f "$MARKER" ]]; then
  bash "$ROOT/scripts/download_mineru_models.sh"
else
  echo "    已存在大模型，仍检查 OCR 小文件是否完整"
  .venv/bin/python "$ROOT/scripts/mineru_ocr_weights.py"
fi

echo "==> 6/7 同步 magic-pdf.json"
python - <<'PY'
import json
from pathlib import Path
root = Path(".").resolve()
cfg = json.loads((root / "config/magic-pdf.json").read_text())
for k in ("temp-output-dir", "models-dir"):
    p = Path(cfg[k])
    if not p.is_absolute():
        cfg[k] = str((root / p).resolve())
Path.home().joinpath("magic-pdf.json").write_text(json.dumps(cfg, indent=2))
print("已同步 ~/magic-pdf.json")
PY

echo "==> 7/7 验证（依赖版本 + magic-pdf 试跑一页）"
python - <<'PY'
import sys
import subprocess
from pathlib import Path

import numpy as np

assert sys.version_info >= (3, 10), sys.version
assert np.__version__.startswith("1.26."), np.__version__
import cv2
import transformers

print("python", sys.version.split()[0])
print("numpy", np.__version__)
print("cv2", cv2.__version__)
print("transformers", transformers.__version__)
if transformers.__version__ >= "4.54":
    raise SystemExit(
        "transformers>=4.54 会导致公式识别失败且 magic-pdf 仍 exit 0；"
        "请执行: pip install -r requirements-mineru.txt --no-deps --force-reinstall"
    )

from paddleocr import PaddleOCR  # noqa: F401

print("paddleocr OK")

root = Path(".").resolve()
pdf = root / "pdf" / "GBT 1568-2008 键 技术条件.pdf"
if not pdf.is_file():
    raise SystemExit(f"缺少试跑 PDF: {pdf}")
out = root / "artifacts" / "mineru" / ".fix_mineru_smoke"
if out.exists():
    import shutil
    shutil.rmtree(out)
out.mkdir(parents=True)
proc = subprocess.run(
    ["magic-pdf", "-p", str(pdf), "-o", str(out), "-m", "ocr"],
    capture_output=True,
    text=True,
    timeout=600,
)
log = (proc.stdout or "") + (proc.stderr or "")
mds = list(out.rglob("*.md"))
if proc.returncode != 0 or not mds:
  tail = "\n".join(log.strip().splitlines()[-15:])
  raise SystemExit(
      f"magic-pdf 试跑未产出 Markdown（code={proc.returncode}）。\n"
      f"日志末尾:\n{tail}"
  )
print("magic-pdf smoke OK:", mds[0])
PY

echo ""
echo "MinerU 环境就绪。验证: .venv/bin/python scripts/run_mineru_poc.py"
echo "完整入库: .venv/bin/python scripts/ingest.py --force-full"
