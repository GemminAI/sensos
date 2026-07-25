"""LLM provider interface for narrative generation."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate narrative text from prompt."""

    async def generate_with_retry(
        self,
        prompt: str,
        *,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await asyncio.wait_for(self.generate(prompt), timeout=timeout)
            except Exception as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"{self.name} failed after {max_retries} attempts: {last_error}") from last_error
