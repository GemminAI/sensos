"""CLE/HEKB clients are transport-only extension points (EXP-Ubuntu011) —
these tests verify the pooled/retried transport works against each
service's real health-check convention, and that no payload-mapping method
(lift/store/etc.) exists yet. Semantic Mapping is EXP-Ubuntu012+.
"""

import httpx

from runtime.core.config import Settings
from runtime.gateway import http_pool
from runtime.gateway.cle_client import CLEClient
from runtime.gateway.hekb_client import HekbClient


def _mock_pooled_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)

    async def fake_get_pooled_client(base_url, profile=None):
        return httpx.AsyncClient(transport=transport, base_url=base_url)

    monkeypatch.setattr(http_pool, "get_pooled_client", fake_get_pooled_client)


async def test_cle_health_check_success(monkeypatch):
    def handler(request):
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok", "service": "cle"})

    _mock_pooled_client(monkeypatch, handler)
    client = CLEClient(Settings(cle_url="http://cle-test:8000"))
    assert await client.health_check() is True


async def test_cle_health_check_unreachable(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    _mock_pooled_client(monkeypatch, handler)
    client = CLEClient(Settings(cle_url="http://cle-test:8000"))
    assert await client.health_check() is False


async def test_cle_generic_call_reaches_real_route_shape(monkeypatch):
    """Proves the transport (pooled/retried) works against CLE's real /lift
    route shape — without this client ever deciding what to send."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"concept_id": "c1"})

    _mock_pooled_client(monkeypatch, handler)
    client = CLEClient(Settings(cle_url="http://cle-test:8000"))

    result = await client.call("POST", "/lift", json={"concept": "x", "subject_context": {}})
    assert captured["path"] == "/lift"
    assert result == {"concept_id": "c1"}


def test_cle_client_has_no_lift_method_yet():
    """Semantic Mapping (Observation -> LiftRequest) is explicitly deferred
    to EXP-Ubuntu012+ — this client must not commit to a payload shape."""
    assert not hasattr(CLEClient, "lift")


async def test_hekb_health_check_success(monkeypatch):
    def handler(request):
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    _mock_pooled_client(monkeypatch, handler)
    client = HekbClient(Settings(hekb_url="http://hekb-test:8080"))
    assert await client.health_check() is True


async def test_hekb_health_check_unreachable(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    _mock_pooled_client(monkeypatch, handler)
    client = HekbClient(Settings(hekb_url="http://hekb-test:8080"))
    assert await client.health_check() is False


def test_hekb_client_has_no_store_method_yet():
    assert not hasattr(HekbClient, "store")
