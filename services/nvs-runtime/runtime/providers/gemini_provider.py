"""Google Gemini narrative provider."""

from __future__ import annotations

import os

import httpx

from runtime.providers.base import LLMProvider


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            from runtime.providers.openai_provider import _mock_narrative

            return _mock_narrative(prompt, "gemini")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
