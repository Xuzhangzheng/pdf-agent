from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParseOutput:
    """统一解析输出，供 structure.py 消费。"""

    backend: str
    page_mds: list[tuple[int, str]]
    md_root: Path | None = None
    artifacts_dir: Path | None = None
    meta: dict = field(default_factory=dict)
