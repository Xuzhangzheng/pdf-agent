from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from src.config.settings import Settings, get_settings
from src.llm.ark_responses import ark_responses_create

logger = logging.getLogger(__name__)

_VL_PROMPT = """你是文档 OCR 校对助手。根据【扫描页图像】核对下面 MinerU OCR 草稿。

要求：
1. 只输出该页应有的 Markdown 正文，不要解释。
2. 只转写图像中可见的文字，禁止添加图中不存在的内容、禁止用外部标准知识补全丢失条款。
3. 保留条款编号（如 3.1、4.1.2）。
4. 符号 ± 不要写成「土」；键宽字母 b 不要写成 6。

【MinerU OCR 草稿】
{draft}
"""


def render_pdf_page_png(pdf_path: Path, page_1based: int, scale: float = 2.0) -> bytes:
    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_1based - 1]
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def build_vl_responses_input(
    *,
    image_data_url: str,
    prompt: str,
) -> list[dict[str, Any]]:
    """与方舟 curl 一致：input_image + input_text。"""
    return [
        {
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": image_data_url},
                {"type": "input_text", "text": prompt},
            ],
        }
    ]


class VlPageCorrector:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def should_correct_page(
        self,
        *,
        gaps: list[str] | None = None,
        low_confidence: bool = False,
        force: bool = False,
    ) -> bool:
        if not self.settings.ocr_vl_correction_enabled:
            return False
        if not self.settings.ark_api_key:
            return False
        if force:
            return True
        return bool(gaps) or low_confidence

    def correct_page(
        self,
        pdf_path: Path,
        page: int,
        draft_text: str,
        *,
        session_id: str | None = None,
    ) -> str:
        png = render_pdf_page_png(
            pdf_path, page, scale=self.settings.ocr_vl_render_scale
        )
        b64 = base64.standard_b64encode(png).decode("ascii")
        image_url = f"data:image/png;base64,{b64}"
        prompt = _VL_PROMPT.format(draft=draft_text[:12000])
        model = self.settings.ark_vl_model
        payload = build_vl_responses_input(image_data_url=image_url, prompt=prompt)
        out = ark_responses_create(
            input_payload=payload,
            model=model,
            temperature=0.0,
            settings=self.settings,
            stage="ocr_vl_correct",
            session_id=session_id,
        )
        logger.info("VL corrected page %s via /responses (%d chars)", page, len(out))
        return out
