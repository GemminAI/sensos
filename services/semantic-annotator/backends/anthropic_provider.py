"""Anthropic (Claude) Semantic Annotator backend."""

from __future__ import annotations

from app.tags import SYSTEM_PROMPT
from backends.base import BaseAnnotatorProvider
from backends.http import http_post_json


class AnthropicProvider(BaseAnnotatorProvider):
    name = "anthropic"

    def __init__(self, *, api_key: str, model: str, timeout: int = 60) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model

    def annotate_raw(self, text: str) -> str:
        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": text}],
        }
        body = http_post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            {
                "content-type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=self._timeout,
        )
        blocks = body.get("content", [])
        return "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
