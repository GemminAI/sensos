"""Google Gemini Semantic Annotator backend."""

from __future__ import annotations

from app.tags import SYSTEM_PROMPT
from backends.base import BaseAnnotatorProvider
from backends.http import http_post_json


class GeminiProvider(BaseAnnotatorProvider):
    name = "gemini"

    def __init__(self, *, api_key: str, model: str, timeout: int = 60) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model

    def annotate_raw(self, text: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent?key={self._api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
            },
        }
        body = http_post_json(
            url,
            payload,
            {"content-type": "application/json"},
            timeout=self._timeout,
        )
        return body["candidates"][0]["content"]["parts"][0]["text"]
