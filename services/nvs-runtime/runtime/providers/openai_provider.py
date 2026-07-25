"""OpenAI narrative provider."""

from __future__ import annotations

import os

import httpx

from runtime.providers.base import LLMProvider


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            return _mock_narrative(prompt, "openai")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 1024,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()


def _mock_narrative(prompt: str, provider: str) -> str:
    snippet = prompt[:120].replace("\n", " ")
    return f"[{provider} mock] Narrative synthesis: {snippet}..."
