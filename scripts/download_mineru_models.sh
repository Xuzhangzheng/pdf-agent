#!/usr/bin/env bash
# 下载 MinerU / magic-pdf 1.3 所需模型到 artifacts/mineru/models
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "请先: bash scripts/setup.sh" >&2
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH="$ROOT"

MODELS_DIR="$ROOT/artifacts/mineru/models"
mkdir -p "$MODELS_DIR"

echo "==> 下载 PDF-Extract-Kit-1.0 到 $MODELS_DIR"
echo "    （体积较大，首次约数 GB，需可访问 huggingface.co 或配置 HF_ENDPOINT 镜像）"

.venv/bin/python - <<'PY'
import os
from pathlib import Path

from huggingface_hub import snapshot_download

root = Path(".").resolve()
models_dir = root / "artifacts" / "mineru" / "models"
models_dir.mkdir(parents=True, exist_ok=True)

repo = os.environ.get("MINERU_MODEL_REPO", "opendatalab/PDF-Extract-Kit-1.0")
print(f"Downloading {repo} -> {models_dir}")
snapshot_download(repo_id=repo, local_dir=str(models_dir))
nested = models_dir / "models"
if nested.is_dir() and (nested / "MFD").exists():
    for child in nested.iterdir():
        dest = models_dir / child.name
        if dest.exists():
            continue
        child.rename(dest)
    nested.rmdir()
marker = models_dir / "MFD" / "YOLO" / "yolo_v8_ft.pt"
if not marker.is_file():
    raise SystemExit(f"下载完成但未找到 {marker}，请检查仓库结构或换用 MINERU_MODEL_REPO")

print("OK:", marker)
PY

.venv/bin/python "$ROOT/scripts/mineru_ocr_weights.py"

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

echo ""
echo "模型就绪。验证: .venv/bin/python scripts/run_mineru_poc.py"
