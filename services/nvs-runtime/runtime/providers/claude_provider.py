"""Anthropic Claude narrative provider."""

from __future__ import annotations

import os

import httpx

from runtime.providers.base import LLMProvider


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            from runtime.providers.openai_provider import _mock_narrative

            return _mock_narrative(prompt, "claude")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            blocks = data.get("content", [])
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
