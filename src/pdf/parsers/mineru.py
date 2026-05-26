from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class MinerUError(RuntimeError):
    pass


def ensure_magic_pdf_config(project_root: Path) -> Path:
    """Ensure ~/magic-pdf.json exists (magic-pdf reads temp-output-dir from it)."""
    home_cfg = Path.home() / "magic-pdf.json"
    template = project_root / "config" / "magic-pdf.json"
    if not home_cfg.exists() and template.exists():
        data = json.loads(template.read_text(encoding="utf-8"))
        temp = data.get("temp-output-dir", "artifacts/mineru")
        if not Path(temp).is_absolute():
            data["temp-output-dir"] = str((project_root / temp).resolve())
        models = data.get("models-dir", "artifacts/mineru/models")
        if not Path(models).is_absolute():
            data["models-dir"] = str((project_root / models).resolve())
        home_cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Created %s from project template", home_cfg)
    if not home_cfg.exists():
        raise MinerUError(
            f"Missing {home_cfg}. Copy config/magic-pdf.json to ~/magic-pdf.json "
            "and set temp-output-dir."
        )
    return home_cfg


def _find_magic_pdf_bin(explicit: str, project_root: Path) -> str:
    if explicit:
        return explicit
    venv_bin = project_root / ".venv" / "bin" / "magic-pdf"
    if venv_bin.exists():
        return str(venv_bin)
    found = shutil.which("magic-pdf")
    if found:
        return found
    raise MinerUError("magic-pdf CLI not found")


def run_mineru(pdf_path: Path, output_dir: Path, mineru_bin: str = "") -> Path:
    """Run magic-pdf pdf-command (OCR); sync markdown into output_dir."""
    from src.config.settings import get_settings

    project_root = get_settings().project_root
    ensure_magic_pdf_config(project_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    bin_path = _find_magic_pdf_bin(mineru_bin, project_root)

    settings = get_settings()
    model_mode = settings.mineru_model_mode.strip() or "full"
    if model_mode not in ("lite", "full"):
        model_mode = "full"

    def _run_once(mode: str) -> subprocess.CompletedProcess[str]:
        cmd = [
            bin_path,
            "pdf-command",
            "--pdf",
            str(pdf_path.resolve()),
            "--method",
            "ocr",
            "--inside_model",
            "true",
            "--model_mode",
            mode,
        ]
        logger.info("Running MinerU: %s", " ".join(cmd))
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
                env=os.environ.copy(),
                cwd=str(project_root),
            )
        except subprocess.TimeoutExpired as e:
            raise MinerUError("MinerU timed out after 900s") from e

    proc = _run_once(model_mode)
    err_text = (proc.stderr or "") + (proc.stdout or "")
    full_deps_missing = "detectron2" in err_text or "full-cpu" in err_text
    if proc.returncode != 0 and model_mode == "full" and full_deps_missing:
        logger.warning(
            "MinerU full mode unavailable (detectron2/full-cpu); falling back to lite"
        )
        proc = _run_once("lite")
        model_mode = "lite"

    if proc.returncode != 0:
        raise MinerUError(
            f"MinerU failed (code {proc.returncode}): {proc.stderr or proc.stdout}"
        )
    logger.info("MinerU finished with model_mode=%s", model_mode)

    from magic_pdf.libs.config_reader import get_local_dir

    local_dir = Path(get_local_dir())
    stem = pdf_path.stem
    candidates = [
        local_dir / "magic-pdf" / stem / "ocr",
        local_dir / "magic-pdf" / stem / "auto",
        local_dir / "magic-pdf" / stem,
    ]
    src_root = None
    for c in candidates:
        if c.exists() and list(c.rglob("*.md")):
            src_root = c
            break
    if src_root is None:
        raise MinerUError(f"No markdown output under {local_dir}/magic-pdf/{stem}")

    dest = output_dir / stem
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src_root, dest)
    md_root = _locate_markdown_root(dest)
    if not md_root:
        raise MinerUError(f"No markdown files copied to {dest}")
    return md_root


def _locate_markdown_root(output_dir: Path) -> Path | None:
    md_files = sorted(output_dir.rglob("*.md"))
    if not md_files:
        return None
    if len(md_files) == 1:
        return md_files[0].parent
    return output_dir


def load_mineru_pages(md_root: Path, page_count: int) -> list[tuple[int, str]]:
    """Return list of (page_1based, markdown_text)."""
    md_files = sorted(md_root.rglob("*.md"))
    if not md_files:
        single = md_root if md_root.suffix == ".md" else None
        if single and single.is_file():
            md_files = [single]
        else:
            raise MinerUError(f"No markdown under {md_root}")

    pages: list[tuple[int, str]] = []
    if len(md_files) == 1:
        text = md_files[0].read_text(encoding="utf-8", errors="replace")
        if page_count <= 1:
            return [(1, text)]
        parts = text.split("\n\n---\n\n")
        if len(parts) >= page_count:
            return [(i + 1, parts[i]) for i in range(page_count)]
        return [(i + 1, text) for i in range(page_count)]

    for idx, mf in enumerate(md_files[:page_count], start=1):
        pages.append((idx, mf.read_text(encoding="utf-8", errors="replace")))

    if len(pages) < page_count and pages:
        combined = pages[0][1]
        return [(i + 1, combined) for i in range(page_count)]
    return pages if pages else [(1, md_files[0].read_text(encoding="utf-8", errors="replace"))]


def load_content_list(md_root: Path) -> list[dict]:
    """读取 MinerU 输出的 *_content_list.json（含 table 图像块）。"""
    for jf in sorted(md_root.rglob("*_content_list.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            continue
    return []


def load_mineru_json_layout(output_dir: Path) -> list[dict]:
    for jf in output_dir.rglob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "pages" in data:
                return data["pages"]
        except json.JSONDecodeError:
            continue
    return []
