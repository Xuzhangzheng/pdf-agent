from __future__ import annotations


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)


def chunk_block_text(text: str, target_tokens: int, overlap_tokens: int) -> list[str]:
    if estimate_tokens(text) <= target_tokens:
        return [text]

    target_chars = target_tokens * 2
    overlap_chars = overlap_tokens * 2
    parts: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + target_chars)
        parts.append(text[start:end].strip())
        if end >= n:
            break
        start = max(0, end - overlap_chars)
    return [p for p in parts if p]
