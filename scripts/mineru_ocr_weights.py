"""补全 magic-pdf 必需的 OCR 权重（HF 镜像常 404 该 LFS 小文件）。"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

OCR_PATCHES: dict[str, tuple[str, int]] = {
    "models/OCR/paddleocr_torch/ch_PP-OCRv3_det_infer.pth": (
        "5e364ffd412f39417db2b4430098cfec7d0f8ed36c859224e3fc036186b91359",
        2_400_000,
    ),
}

# main 分支已删除该文件，需固定到仍含 OCR v3 权重的提交
HF_OCR_REVISION = "95b05fd7bb529772a11092cca20c06f66bea2cbc"

MODELSCOPE_IDS = (
    "opendatalab/PDF-Extract-Kit-1.0",
    "OpenDataLab/PDF-Extract-Kit-1.0",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ocr_patch_ok(dest: Path, expected_sha256: str, min_bytes: int) -> bool:
    return (
        dest.is_file()
        and not dest.is_symlink()
        and dest.stat().st_size >= min_bytes
        and _sha256(dest) == expected_sha256
    )


def _install_modelscope() -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "modelscope>=1.11.0"],
        check=True,
    )


def _fetch_hf(rel: str, models_dir: Path, repo: str, *, use_mirror: bool) -> Path:
    from huggingface_hub import hf_hub_download

    env = os.environ.copy()
    if use_mirror:
        env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    else:
        env.pop("HF_ENDPOINT", None)
    prev = os.environ.get("HF_ENDPOINT")
    try:
        if use_mirror:
            os.environ["HF_ENDPOINT"] = env["HF_ENDPOINT"]
        else:
            os.environ.pop("HF_ENDPOINT", None)
        fetched = hf_hub_download(
            repo_id=repo,
            filename=rel,
            revision=HF_OCR_REVISION,
            local_dir=str(models_dir),
        )
    finally:
        if prev is None:
            os.environ.pop("HF_ENDPOINT", None)
        else:
            os.environ["HF_ENDPOINT"] = prev
    return Path(fetched)


def _fetch_modelscope(rel: str, models_dir: Path) -> Path:
    try:
        from modelscope.hub.file_download import model_file_download
    except ImportError:
        _install_modelscope()
        from modelscope.hub.file_download import model_file_download

    last_err: Exception | None = None
    for model_id in MODELSCOPE_IDS:
        try:
            return Path(
                model_file_download(
                    model_id=model_id,
                    file_path=rel,
                    cache_dir=str(models_dir / ".modelscope_cache"),
                )
            )
        except Exception as e:
            last_err = e
    raise RuntimeError(f"ModelScope 下载失败: {last_err}") from last_err


def _fetch_curl(rel: str, dest: Path) -> None:
    """直连 HuggingFace CDN（不经过 hf-mirror）。"""
    urls = [
        f"https://huggingface.co/opendatalab/PDF-Extract-Kit-1.0/resolve/"
        f"{HF_OCR_REVISION}/{rel}",
        f"https://cdn-lfs.huggingface.co/repos/95/b0/{HF_OCR_REVISION}/"
        f"4f6b1f3d9b52dca0f731a2c3e30cd417f7f9b501a09bc5b08683e8624632dd63?download=true",
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        last_err: Exception | None = None
        for url in urls:
            try:
                urlretrieve(url, tmp_path)  # noqa: S310
                shutil.move(str(tmp_path), dest)
                return
            except Exception as e:
                last_err = e
        raise RuntimeError(f"curl/urllib 下载失败: {last_err}") from last_err
    finally:
        tmp_path.unlink(missing_ok=True)


def _place_file(got: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if got.resolve() == dest.resolve():
        return
    if dest.exists():
        dest.unlink()
    shutil.copy2(got, dest)


def ensure_ocr_patches(
    models_dir: Path,
    repo: str | None = None,
    *,
    verbose: bool = True,
) -> None:
    repo = repo or os.environ.get("MINERU_MODEL_REPO", "opendatalab/PDF-Extract-Kit-1.0")
    models_dir = models_dir.resolve()
    models_dir.mkdir(parents=True, exist_ok=True)

    for rel, (expected_sha256, min_bytes) in OCR_PATCHES.items():
        dest = models_dir / rel.removeprefix("models/")
        if dest.is_symlink():
            dest.unlink()
        if ocr_patch_ok(dest, expected_sha256, min_bytes):
            if verbose:
                print(f"OK {dest.name}")
            continue

        if verbose:
            print(f"补下 {rel} ...")

        errors: list[str] = []
        got: Path | None = None

        for label, fetcher in (
            ("HuggingFace 直连", lambda: _fetch_hf(rel, models_dir, repo, use_mirror=False)),
            ("HuggingFace 镜像", lambda: _fetch_hf(rel, models_dir, repo, use_mirror=True)),
            ("ModelScope", lambda: _fetch_modelscope(rel, models_dir)),
        ):
            try:
                got = fetcher()
                if verbose:
                    print(f"    成功: {label}")
                break
            except Exception as e:
                errors.append(f"{label}: {e}")
                if verbose:
                    print(f"    失败: {label} — {e}")

        if got is None:
            try:
                _fetch_curl(rel, dest)
                got = dest
                if verbose:
                    print("    成功: HuggingFace CDN 直链")
            except Exception as e:
                errors.append(f"CDN: {e}")

        if got is not None and got.resolve() != dest.resolve():
            _place_file(got, dest)

        if not ocr_patch_ok(dest, expected_sha256, min_bytes):
            msg = "\n".join(errors)
            raise SystemExit(
                f"无法下载 {dest.name}。\n"
                f"已尝试: HuggingFace 直连/镜像、ModelScope、CDN。\n{msg}\n"
                "可手动下载后放到:\n"
                f"  {dest}\n"
                "  https://huggingface.co/opendatalab/PDF-Extract-Kit-1.0/"
                "tree/main/models/OCR/paddleocr_torch"
            )
        if verbose:
            print(f"    校验通过 {dest.name} ({dest.stat().st_size} bytes)")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    models_dir = root / "artifacts" / "mineru" / "models"
    ensure_ocr_patches(models_dir)


if __name__ == "__main__":
    main()
