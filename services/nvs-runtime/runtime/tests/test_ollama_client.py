"""Tests for runtime.gateway.ollama_client — mocked transport, same
`_mock_pooled_client` convention as test_extension_point_clients.py.
"""

import json

import httpx
from runtime.core.config import Settings
from runtime.gateway import http_pool
from runtime.gateway.ollama_client import OllamaClient


def _mock_pooled_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)

    async def fake_get_pooled_client(base_url, profile=None):
        return httpx.AsyncClient(transport=transport, base_url=base_url)

    monkeypatch.setattr(http_pool, "get_pooled_client", fake_get_pooled_client)


async def test_health_check_success(monkeypatch):
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": []})

    _mock_pooled_client(monkeypatch, handler)
    client = OllamaClient(Settings(ollama_url="http://ollama-test:11434"))
    assert await client.health_check() is True


async def test_health_check_unreachable(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    _mock_pooled_client(monkeypatch, handler)
    client = OllamaClient(Settings(ollama_url="http://ollama-test:11434"))
    assert await client.health_check() is False


async def test_generate_posts_real_route_shape(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gpt-oss:20b",
                "response": "the summary",
                "done": True,
                "done_reason": "stop",
                "eval_count": 12,
                "total_duration": 123456789,
            },
        )

    _mock_pooled_client(monkeypatch, handler)
    client = OllamaClient(Settings(ollama_url="http://ollama-test:11434"))
    result = await client.generate("gpt-oss:20b", "hello", temperature=0.0, seed=42)

    assert captured["path"] == "/api/generate"
    assert captured["json"] == {
        "model": "gpt-oss:20b",
        "prompt": "hello",
        "stream": False,
        "options": {"temperature": 0.0, "seed": 42},
    }
    assert result["response"] == "the summary"


async def test_digest_of_finds_matching_model(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "gpt-oss:20b", "digest": "abc123", "size": 1}]},
        )

    _mock_pooled_client(monkeypatch, handler)
    client = OllamaClient(Settings(ollama_url="http://ollama-test:11434"))
    assert await client.digest_of("gpt-oss:20b") == "abc123"


async def test_digest_of_missing_model_returns_none(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": []})

    _mock_pooled_client(monkeypatch, handler)
    client = OllamaClient(Settings(ollama_url="http://ollama-test:11434"))
    assert await client.digest_of("gpt-oss:20b") is None
