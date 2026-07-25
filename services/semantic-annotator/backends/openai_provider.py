"""OpenAI Semantic Annotator backend."""

from __future__ import annotations

from app.tags import SYSTEM_PROMPT
from backends.base import BaseAnnotatorProvider
from backends.http import http_post_json


class OpenAIProvider(BaseAnnotatorProvider):
    name = "openai"

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
            "temperature": 0.0,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        body = http_post_json(
            "https://api.openai.com/v1/chat/completions",
            payload,
            {
                "content-type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            timeout=self._timeout,
        )
        return body["choices"][0]["message"]["content"]
