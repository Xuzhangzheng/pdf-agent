from __future__ import annotations

import json
import logging
from pathlib import Path

from src.config.settings import Settings, get_settings
from src.llm.ark_client import ArkClient
from src.models.blocks import Chunk

logger = logging.getLogger(__name__)

_PROMPT = """你是标准文档检索助手。根据下面「证据片段」，生成 {n} 个用户可能会问的中文问题。

要求：
1. 问题必须能被该片段直接回答，不要编造片段中未出现的概念、数值或条款号。
2. 可包含口语化问法（如「这标准管啥的」对应范围类片段）。
3. 若片段是表格，问题应涉及表号、尺寸、公差、AQL 等表中可见信息。
4. 只输出 JSON 数组，元素为字符串，不要 markdown，不要解释。

【证据片段】
{text}
"""


def _cache_path(settings: Settings) -> Path:
    return settings.resolve_path(settings.parsed_output_dir) / "hypothetical_questions.json"


def load_questions_cache(settings: Settings | None = None) -> dict[str, list[str]] | None:
    settings = settings or get_settings()
    path = _cache_path(settings)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {k: list(v) for k, v in raw.items()}
    except Exception as e:
        logger.warning("Failed to load question cache %s: %s", path, e)
        return None


def save_questions_cache(
    mapping: dict[str, list[str]], settings: Settings | None = None
) -> Path:
    settings = settings or get_settings()
    path = _cache_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def generate_questions_for_chunks(
    chunks: list[Chunk],
    *,
    settings: Settings | None = None,
    session_id: str | None = None,
    force_regenerate: bool = False,
) -> dict[str, list[str]]:
    """为每个 chunk 生成预设问句；返回 chunk_id -> questions。"""
    settings = settings or get_settings()
    n = max(1, settings.index_questions_per_chunk)

    if not force_regenerate:
        cached = load_questions_cache(settings)
        if cached is not None and all(c.chunk_id in cached for c in chunks):
            return {c.chunk_id: cached[c.chunk_id][:n] for c in chunks}

    if not settings.ark_api_key:
        raise ValueError("ARK_API_KEY is required for hypothetical question generation")

    ark = ArkClient(settings)
    out: dict[str, list[str]] = {}
    for c in chunks:
        snippet = (c.text or "").strip()[:2000]
        if not snippet:
            out[c.chunk_id] = []
            continue
        messages = [
            {
                "role": "user",
                "content": _PROMPT.format(n=n, text=snippet),
            }
        ]
        try:
            raw = ark.chat(
                messages,
                temperature=0.0,
                json_mode=True,
                stage="index_hypothetical_questions",
                session_id=session_id,
            )
            parsed = ark.parse_json(raw)
            if isinstance(parsed, list):
                qs = [str(x).strip() for x in parsed if str(x).strip()]
            elif isinstance(parsed, dict) and "questions" in parsed:
                qs = [str(x).strip() for x in parsed["questions"] if str(x).strip()]
            else:
                qs = []
        except Exception as e:
            logger.warning("Question gen failed for %s: %s", c.chunk_id, e)
            qs = []
        out[c.chunk_id] = qs[:n]

    save_questions_cache(out, settings)
    return out
