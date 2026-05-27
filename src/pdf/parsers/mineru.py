from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class MinerUError(RuntimeError):
    pass


def ensure_magic_pdf_config(project_root: Path) -> Path:
    """Ensure ~/magic-pdf.json exists and paths point at this project."""
    home_cfg = Path.home() / "magic-pdf.json"
    template = project_root / "config" / "magic-pdf.json"
    if not template.exists():
        if not home_cfg.exists():
            raise MinerUError(
                f"Missing {home_cfg}. Copy config/magic-pdf.json to ~/magic-pdf.json "
                "and set temp-output-dir."
            )
        return home_cfg

    data = json.loads(template.read_text(encoding="utf-8"))
    for key in ("temp-output-dir", "models-dir"):
        p = Path(data.get(key, ""))
        if p and not p.is_absolute():
            data[key] = str((project_root / p).resolve())

    project_models = Path(data["models-dir"])
    if home_cfg.exists():
        try:
            existing = json.loads(home_cfg.read_text(encoding="utf-8"))
            for key in ("temp-output-dir", "models-dir"):
                existing[key] = data[key]
            for key in ("layout-config", "formula-config", "table-config"):
                if key in data:
                    existing[key] = data[key]
            home_cfg.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            logger.info("Synced %s paths from project template", home_cfg)
        except (json.JSONDecodeError, OSError):
            home_cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info("Rewrote %s from project template", home_cfg)
    else:
        home_cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Created %s from project template", home_cfg)

    if not (project_models / "MFD" / "YOLO" / "yolo_v8_ft.pt").is_file():
        logger.warning(
            "MinerU model marker missing at %s — run: bash scripts/download_mineru_models.sh",
            project_models / "MFD" / "YOLO" / "yolo_v8_ft.pt",
        )
    return home_cfg


def _mineru_log_indicates_failure(err_text: str) -> bool:
    """magic-pdf 常在异常时仍 exit 0，需扫日志。"""
    if not err_text.strip():
        return False
    markers = (
        "TypeError:",
        "KeyError:",
        "ModuleNotFoundError",
        "FileNotFoundError",
        "RuntimeError:",
        "No such file or directory",
        "| ERROR    |",
    )
    return any(m in err_text for m in markers)


def _interpret_mineru_log(err_text: str, models_dir: Path) -> str | None:
    """从 magic-pdf 日志推断失败原因（CLI 常 exit 0 但 stderr 有异常）。"""
    if "cache_position" in err_text:
        return (
            "transformers 版本过新，公式识别 (UniMERNet) 不兼容。"
            "请执行: pip install -r requirements-mineru.txt --no-deps --force-reinstall"
        )
    if "Cache only has 0 layers" in err_text:
        return (
            "transformers 4.54.x 与 UniMERNet 不兼容。"
            "请锁定: pip install transformers==4.52.4 --no-deps --force-reinstall"
        )
    if "ModuleNotFoundError" in err_text:
        m = re.search(r"No module named '([^']+)'", err_text)
        mod = m.group(1) if m else "unknown"
        if mod == "detectron2":
            return (
                f"缺少 Python 依赖 {mod}（layoutlmv3 需要）。"
                "请确认 ~/magic-pdf.json 含 layout-config.model=doclayout_yolo，"
                "并重新运行: bash scripts/fix_mineru_env.sh"
            )
        return (
            f"缺少 Python 依赖 {mod}。请运行: bash scripts/fix_mineru_env.sh"
        )
    marker = models_dir / "MFD" / "YOLO" / "yolo_v8_ft.pt"
    if "yolo_v8_ft.pt" in err_text and "No such file" in err_text:
        if marker.is_file():
            return (
                f"magic-pdf 未在 models-dir 找到 yolo_v8_ft.pt，但项目内存在 {marker}。"
                f"请检查 ~/magic-pdf.json 的 models-dir 是否为: {models_dir}"
            )
        return "MinerU 模型文件缺失。请执行: bash scripts/download_mineru_models.sh"
    ocr_v3 = models_dir / "OCR" / "paddleocr_torch" / "ch_PP-OCRv3_det_infer.pth"
    if "ch_PP-OCRv3_det_infer.pth" in err_text:
        if ocr_v3.is_symlink():
            return (
                "ch_PP-OCRv3_det_infer.pth 不能链到 v5 权重（架构不兼容）。"
                "请删除该符号链接后执行: bash scripts/download_mineru_models.sh"
            )
        if marker.is_file():
            return (
                "OCR 检测权重 ch_PP-OCRv3_det_infer.pth 缺失或不完整（与 yolo 等大文件无关）。"
                "请执行: bash scripts/download_mineru_models.sh"
            )
    if "size mismatch" in err_text and "state_dict" in err_text:
        return (
            "OCR 权重版本不匹配（常见原因：用 v5 文件冒充 v3）。"
            "请删除 artifacts/mineru/models/OCR/paddleocr_torch/ch_PP-OCRv3_det_infer.pth "
            "后执行: bash scripts/download_mineru_models.sh"
        )
    return None


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


def _magic_pdf_cli_style(bin_path: str) -> str:
    """Return 'v2' (-p/-o) or 'legacy' (pdf-command --pdf)."""
    try:
        proc = subprocess.run(
            [bin_path, "--help"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        help_text = (proc.stdout or "") + (proc.stderr or "")
    except (subprocess.TimeoutExpired, OSError):
        return "legacy"
    if re.search(r"^\s+-p,\s+--path\b", help_text, re.MULTILINE):
        return "v2"
    if "pdf-command" in help_text:
        return "legacy"
    return "v2"


def mineru_cli_available(
    mineru_bin: str = "",
    project_root: Path | None = None,
) -> bool:
    """当前环境是否可调用 magic-pdf（未安装时 mineru 的 force_full ingest 会失败）。"""
    from src.config.settings import get_settings

    root = project_root or get_settings().project_root
    try:
        _find_magic_pdf_bin(mineru_bin, root)
        return True
    except MinerUError:
        return False


def run_mineru(pdf_path: Path, output_dir: Path, mineru_bin: str = "") -> Path:
    """Run magic-pdf OCR; sync markdown into output_dir."""
    from src.config.settings import get_settings

    project_root = get_settings().project_root
    ensure_magic_pdf_config(project_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    bin_path = _find_magic_pdf_bin(mineru_bin, project_root)
    cli_style = _magic_pdf_cli_style(bin_path)

    settings = get_settings()
    model_mode = settings.mineru_model_mode.strip() or "full"
    if model_mode not in ("lite", "full"):
        model_mode = "full"

    work_dir = output_dir.parent / f".mineru_run_{pdf_path.stem}"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    def _run_v2() -> subprocess.CompletedProcess[str]:
        cmd = [
            bin_path,
            "-p",
            str(pdf_path.resolve()),
            "-o",
            str(work_dir.resolve()),
            "-m",
            "ocr",
        ]
        logger.info("Running MinerU (CLI v2): %s", " ".join(cmd))
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
            env=os.environ.copy(),
            cwd=str(project_root),
        )

    def _run_legacy(mode: str) -> subprocess.CompletedProcess[str]:
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
        logger.info("Running MinerU (legacy CLI): %s", " ".join(cmd))
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
            env=os.environ.copy(),
            cwd=str(project_root),
        )

    try:
        if cli_style == "v2":
            proc = _run_v2()
            used_mode = "v2-ocr"
        else:
            proc = _run_legacy(model_mode)
            err_text = (proc.stderr or "") + (proc.stdout or "")
            full_deps_missing = "detectron2" in err_text or "full-cpu" in err_text
            if proc.returncode != 0 and model_mode == "full" and full_deps_missing:
                logger.warning(
                    "MinerU full mode unavailable; falling back to lite"
                )
                proc = _run_legacy("lite")
                model_mode = "lite"
            used_mode = model_mode
    except subprocess.TimeoutExpired as e:
        raise MinerUError("MinerU timed out after 900s") from e

    err_text = (proc.stderr or "") + (proc.stdout or "")
    models_dir = project_root / "artifacts" / "mineru" / "models"
    try:
        cfg = json.loads((Path.home() / "magic-pdf.json").read_text(encoding="utf-8"))
        models_dir = Path(cfg.get("models-dir", models_dir))
    except (json.JSONDecodeError, OSError):
        pass

    if proc.returncode != 0:
        raise MinerUError(f"MinerU failed (code {proc.returncode}): {err_text}")
    if _mineru_log_indicates_failure(err_text):
        log_hint = _interpret_mineru_log(err_text, models_dir)
        tail = "\n".join(err_text.strip().splitlines()[-12:])
        msg = log_hint or f"magic-pdf 日志含错误但未生成 Markdown。\n{tail}"
        raise MinerUError(msg)
    log_hint = _interpret_mineru_log(err_text, models_dir)
    if log_hint:
        raise MinerUError(log_hint)
    logger.info("MinerU finished with cli=%s mode=%s", cli_style, used_mode)

    stem = pdf_path.stem
    if cli_style == "v2":
        src_root = _find_md_root_under(work_dir, stem, project_root)
        if src_root is None:
            hint = _interpret_mineru_log(err_text, models_dir)
            if hint:
                raise MinerUError(hint)
            marker = models_dir / "MFD" / "YOLO" / "yolo_v8_ft.pt"
            if marker.is_file():
                tail = "\n".join(err_text.strip().splitlines()[-12:]) if err_text.strip() else ""
                extra = f"\n日志末尾:\n{tail}" if tail else ""
                raise MinerUError(
                    f"MinerU 未生成 Markdown。模型目录已存在: {models_dir}。"
                    "常见原因：transformers 版本过新（公式识别崩溃）或 OCR 权重缺失；"
                    "请运行: bash scripts/fix_mineru_env.sh"
                    f"{extra}"
                )
            raise MinerUError(
                f"No markdown under {work_dir}. "
                "请运行: bash scripts/download_mineru_models.sh"
            )
    else:
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

    dest = output_dir
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src_root, dest)
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)

    md_root = _locate_markdown_root(dest)
    if not md_root:
        raise MinerUError(f"No markdown files copied to {dest}")
    return md_root


def _find_md_root_under(
    base: Path, pdf_stem: str, project_root: Path | None = None
) -> Path | None:
    """MinerU 1.3 输出: {output_dir}/{stem}/ocr/*.md 或 temp-output-dir/magic-pdf/..."""
    candidates: list[Path] = [
        base / pdf_stem / "ocr",
        base / pdf_stem / "auto",
        base / pdf_stem,
        base / "magic-pdf" / pdf_stem / "ocr",
        base / "magic-pdf" / pdf_stem / "auto",
    ]
    if project_root is not None:
        mineru_root = project_root / "artifacts" / "mineru"
        candidates.extend(
            [
                mineru_root / "magic-pdf" / pdf_stem / "ocr",
                mineru_root / pdf_stem / pdf_stem,
            ]
        )
    for cand in candidates:
        if cand.exists() and list(cand.rglob("*.md")):
            found = _locate_markdown_root(cand)
            if found:
                return found
    md_files = sorted(base.rglob("*.md"))
    if not md_files:
        return None
    if len(md_files) == 1:
        return md_files[0].parent
    return _locate_markdown_root(base) or md_files[0].parent


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
