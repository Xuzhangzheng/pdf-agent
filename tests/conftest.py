from __future__ import annotations

import os
import sys

if sys.platform == "darwin":
    os.environ.setdefault("NPY_DISABLE_MACOS_ACCELERATE", "1")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
