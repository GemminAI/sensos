import pytest

from runtime.providers.router import ORIGIN_ROUTING, generate_narrative, resolve_provider


@pytest.mark.asyncio
async def test_resolve_provider_by_origin():
    assert resolve_provider("jp").name == "gemini"
    assert resolve_provider("us").name == "openai"
    assert resolve_provider("eu").name == "claude"


@pytest.mark.asyncio
async def test_generate_narrative_mock():
    text, provider = await generate_narrative("Summarize this article about trade.", "us")
    assert "mock" in text.lower() or len(text) > 10
    assert provider in ORIGIN_ROUTING.values()
