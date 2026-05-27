from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Iterator

from openai import BadRequestError, OpenAI

from src.config.settings import Settings, get_settings
from src.observability.usage import log_usage

logger = logging.getLogger(__name__)


def _json_format_unsupported(err: BaseException) -> bool:
    text = str(err).lower()
    return "response_format" in text or "json_object" in text


class ArkClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            if not self.settings.ark_api_key:
                raise ValueError("ARK_API_KEY is required")
            self._client = OpenAI(
                api_key=self.settings.ark_api_key,
                base_url=self.settings.ark_base_url,
            )
        return self._client

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        json_mode: bool = False,
        stage: str = "generate",
        question_id: str | None = None,
        session_id: str | None = None,
        retrieval_round: int = 0,
    ) -> str:
        if not self.settings.ark_api_key:
            raise ValueError("ARK_API_KEY is required")

        kwargs: dict[str, Any] = {
            "model": self.settings.ark_chat_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.settings.ark_temperature,
        }
        use_json_format = json_mode and self.settings.ark_chat_json_mode
        if use_json_format:
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except BadRequestError as e:
            if use_json_format and _json_format_unsupported(e):
                logger.info(
                    "Model %s does not support json_object; retrying without response_format",
                    self.settings.ark_chat_model,
                )
                kwargs.pop("response_format", None)
                resp = self.client.chat.completions.create(**kwargs)
            else:
                raise
        latency = int((time.perf_counter() - t0) * 1000)
        usage = resp.usage
        content = resp.choices[0].message.content or ""
        log_usage(
            stage=stage,
            model=self.settings.ark_chat_model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            latency_ms=latency,
            question_id=question_id,
            retrieval_round=retrieval_round,
            session_id=session_id,
            input={"messages": messages},
            output={"content": content},
        )
        return content

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        stage: str = "generate",
        question_id: str | None = None,
        session_id: str | None = None,
        retrieval_round: int = 0,
    ) -> Iterator[str]:
        if not self.settings.ark_api_key:
            raise ValueError("ARK_API_KEY is required")

        kwargs: dict[str, Any] = {
            "model": self.settings.ark_chat_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.settings.ark_temperature,
            "stream": True,
        }

        t0 = time.perf_counter()
        stream = self.client.chat.completions.create(**kwargs)
        parts: list[str] = []
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                parts.append(delta)
                yield delta
        latency = int((time.perf_counter() - t0) * 1000)
        full = "".join(parts)
        log_usage(
            stage=stage,
            model=self.settings.ark_chat_model,
            prompt_tokens=0,
            completion_tokens=max(len(full) // 2, 1),
            total_tokens=max(len(full) // 2, 1),
            latency_ms=latency,
            question_id=question_id,
            session_id=session_id,
            retrieval_round=retrieval_round,
            extra={"stream_estimated_tokens": True},
            input={"messages": messages},
            output={"content": full},
        )

    @staticmethod
    def _fix_invalid_json_escapes(text: str) -> str:
        """LLM 常在 critique 里写 LaTeX（如 \\geq），需把字符串内非法转义加倍。"""
        out: list[str] = []
        i = 0
        in_string = False
        while i < len(text):
            ch = text[i]
            if not in_string:
                if ch == '"':
                    in_string = True
                out.append(ch)
                i += 1
                continue
            if ch == "\\":
                if i + 1 >= len(text):
                    out.append("\\\\")
                    i += 1
                    continue
                nxt = text[i + 1]
                if nxt == "u" and i + 5 < len(text):
                    seq = text[i : i + 6]
                    hex_part = text[i + 2 : i + 6]
                    if all(c in "0123456789abcdefABCDEF" for c in hex_part):
                        out.append(seq)
                        i += 6
                        continue
                if nxt in '"\\/bfnrtu':
                    out.append(ch)
                    out.append(nxt)
                    i += 2
                    continue
                out.append("\\\\")
                out.append(nxt)
                i += 2
                continue
            if ch == '"':
                in_string = False
            out.append(ch)
            i += 1
        return "".join(out)

    @classmethod
    def parse_json(cls, text: str) -> Any:
        text = text.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        last_err: json.JSONDecodeError | None = None
        for candidate in (text, cls._fix_invalid_json_escapes(text)):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as e:
                last_err = e
        assert last_err is not None
        raise last_err
