"""Provider routing: jp→Gemini, us→OpenAI, eu→Claude with fallback."""

from __future__ import annotations

from runtime.providers.base import LLMProvider
from runtime.providers.claude_provider import ClaudeProvider
from runtime.providers.gemini_provider import GeminiProvider
from runtime.providers.openai_provider import OpenAIProvider

ORIGIN_ROUTING: dict[str, str] = {
    "jp": "gemini",
    "us": "openai",
    "eu": "claude",
    "uk": "claude",
    "cn": "gemini",
}

FALLBACK_ORDER = ["gemini", "openai", "claude"]


def _build_provider(name: str) -> LLMProvider:
    if name == "gemini":
        return GeminiProvider()
    if name == "openai":
        return OpenAIProvider()
    if name == "claude":
        return ClaudeProvider()
    raise ValueError(f"Unknown provider: {name}")


def resolve_provider(origin: str) -> LLMProvider:
    key = origin.strip().lower()
    provider_name = ORIGIN_ROUTING.get(key, "openai")
    return _build_provider(provider_name)


async def generate_narrative(prompt: str, origin: str) -> tuple[str, str]:
    """Generate narrative with primary provider and fallback chain."""
    primary_name = ORIGIN_ROUTING.get(origin.strip().lower(), "openai")
    chain = [primary_name] + [p for p in FALLBACK_ORDER if p != primary_name]

    last_error: Exception | None = None
    for name in chain:
        provider = _build_provider(name)
        try:
            text = await provider.generate_with_retry(prompt, max_retries=3, timeout=30.0)
            return text, name
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"All providers failed: {last_error}") from last_error
