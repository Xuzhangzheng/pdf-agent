from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

from src.config.settings import Settings, get_settings
from src.llm.ark_client import ArkClient
from src.models.blocks import Chunk

logger = logging.getLogger(__name__)

_RETRY_HINT = (
    "上次输出不是合法 JSON 数组。请只输出形如 [\"问题1\", \"问题2\"] 的 JSON，"
    "字符串内不要出现未转义的双引号，不要 markdown，不要解释。"
)

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


def _questions_from_parsed(parsed: Any) -> list[str]:
    if isinstance(parsed, list):
        return [str(x).strip() for x in parsed if str(x).strip()]
    if isinstance(parsed, dict):
        for key in ("questions", "items", "data"):
            val = parsed.get(key)
            if isinstance(val, list):
                return [str(x).strip() for x in val if str(x).strip()]
    return []


def extract_questions_from_llm_text(raw: str) -> list[str]:
    """从 LLM 原始输出解析问句列表；parse_json 失败时做数组截取与引号抽取。"""
    text = (raw or "").strip()
    if not text:
        return []
    try:
        return _questions_from_parsed(ArkClient.parse_json(text))
    except json.JSONDecodeError:
        pass

    start, end = text.find("["), text.rfind("]")
    if start >= 0 and end > start:
        snippet = text[start : end + 1]
        for candidate in (snippet, ArkClient._fix_invalid_json_escapes(snippet)):
            try:
                parsed = json.loads(candidate)
                qs = _questions_from_parsed(parsed)
                if qs:
                    return qs
            except json.JSONDecodeError:
                continue

    quoted = re.findall(r'"((?:[^"\\]|\\.)*)"', text)
    qs: list[str] = []
    for q in quoted:
        if "\\" in q:
            try:
                q = bytes(q, "utf-8").decode("unicode_escape")
            except ValueError:
                pass
        qs.append(q.strip())
    return [q for q in qs if len(q) >= 4]


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
    on_chunk_progress: Callable[[int, int], None] | None = None,
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
    total = len(chunks)
    for idx, c in enumerate(chunks, start=1):
        if on_chunk_progress is not None:
            on_chunk_progress(idx, total)
        snippet = (c.text or "").strip()[:2000]
        if not snippet:
            out[c.chunk_id] = []
            continue
        messages: list[dict[str, str]] = [
            {
                "role": "user",
                "content": _PROMPT.format(n=n, text=snippet),
            }
        ]
        qs: list[str] = []
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                raw = ark.chat(
                    messages,
                    temperature=0.0,
                    json_mode=True,
                    stage="index_hypothetical_questions",
                    session_id=session_id,
                )
                qs = extract_questions_from_llm_text(raw)
                if qs:
                    break
                last_err = ValueError("empty question list from model")
            except Exception as e:
                last_err = e
            if attempt < 2:
                messages.append({"role": "user", "content": _RETRY_HINT})

        if not qs:
            logger.warning(
                "Question gen failed for %s (ingest continues; chunk has no "
                "hypothetical question vectors): %s",
                c.chunk_id,
                last_err,
            )
        out[c.chunk_id] = qs[:n]
        if idx % 10 == 0:
            save_questions_cache(out, settings)

    save_questions_cache(out, settings)
    return out
