import httpx
import pytest

from runtime.core.network_profile import NetworkProfile
from runtime.gateway import http_pool
from runtime.gateway.http_pool import RetryExhaustedError, get_pooled_client, request_with_retry

# Pool cleanup between tests is handled by the autouse
# _reset_pooled_http_clients fixture in conftest.py.


def _profile(**overrides) -> NetworkProfile:
    base = dict(
        mode="test",
        base_rtt_ms=1,
        request_timeout_ms=200,
        connect_timeout_ms=100,
        retry_count=2,
        retry_backoff_ms=1,  # keep tests fast
        keep_alive=True,
        async_only=True,
        batch_size=5,
        max_keepalive_connections=20,
        max_connections=50,
    )
    base.update(overrides)
    return NetworkProfile(**base)


async def test_pooled_client_is_reused_across_calls():
    """Persistent Connection / Reuse: no caller should open a new TCP
    connection (i.e. a new AsyncClient) per request."""
    profile = _profile()
    first = await get_pooled_client("http://example-a", profile)
    second = await get_pooled_client("http://example-a", profile)
    assert first is second


async def test_different_base_urls_get_different_clients():
    profile = _profile()
    a = await get_pooled_client("http://example-b", profile)
    b = await get_pooled_client("http://example-c", profile)
    assert a is not b


async def test_timeout_and_limits_sourced_from_profile():
    profile = _profile(request_timeout_ms=1500, connect_timeout_ms=300, max_connections=50)
    client = await get_pooled_client("http://example-d", profile)
    assert client.timeout.connect == pytest.approx(0.3)
    assert client.timeout.read == pytest.approx(1.5)


async def test_request_with_retry_succeeds_after_transient_failures(monkeypatch):
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    async def fake_get_pooled_client(base_url, profile=None):
        return httpx.AsyncClient(transport=transport, base_url=base_url)

    monkeypatch.setattr(http_pool, "get_pooled_client", fake_get_pooled_client)

    response = await request_with_retry("GET", "http://example-e", "/ping", profile=_profile(retry_count=3))
    assert response.status_code == 200
    assert len(attempts) == 3


async def test_request_with_retry_raises_after_exhausting_retries(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)

    async def fake_get_pooled_client(base_url, profile=None):
        return httpx.AsyncClient(transport=transport, base_url=base_url)

    monkeypatch.setattr(http_pool, "get_pooled_client", fake_get_pooled_client)

    with pytest.raises(RetryExhaustedError):
        await request_with_retry("GET", "http://example-f", "/ping", profile=_profile(retry_count=2))


async def test_4xx_response_is_not_retried(monkeypatch):
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)

    async def fake_get_pooled_client(base_url, profile=None):
        return httpx.AsyncClient(transport=transport, base_url=base_url)

    monkeypatch.setattr(http_pool, "get_pooled_client", fake_get_pooled_client)

    response = await request_with_retry("GET", "http://example-g", "/missing", profile=_profile(retry_count=3))
    assert response.status_code == 404
    assert len(attempts) == 1
