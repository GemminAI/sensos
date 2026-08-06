"""CLE/HEKB clients: pooled/retried transport (EXP-Ubuntu011) plus the
Semantic Mapping payload methods `lift()`/`store()` (EXP-Ubuntu012B).
"""

import httpx

from runtime.core.config import Settings
from runtime.gateway import http_pool
from runtime.gateway.cle_client import CLEClient
from runtime.gateway.hekb_client import HekbClient, build_hekb_object


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


async def test_cle_lift_posts_concept_shaped_from_position(monkeypatch):
    """EXP-Ubuntu012B: lift() wraps a position vector in CLE's existing
    ConceptInput/MeaningStatePoint shape and posts it to the real /lift
    route — no new CLE payload shape invented."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"concept_id": "c1", "normalized_hash": "h1"})

    _mock_pooled_client(monkeypatch, handler)
    client = CLEClient(Settings(cle_url="http://cle-test:8000"))

    result = await client.lift([0.1, 0.2, 0.3])

    assert captured["path"] == "/lift"
    assert captured["json"] == {"concept": {"states": [{"theta": [0.1, 0.2, 0.3]}]}}
    assert result == {"concept_id": "c1", "normalized_hash": "h1"}


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


async def test_hekb_store_posts_object_to_v1_objects(monkeypatch):
    """EXP-Ubuntu012B: store() posts to the real POST /v1/objects and
    returns the {object_id, hash, timestamp} response verbatim."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(
            201, json={"object_id": "a" * 64, "hash": "a" * 64, "timestamp": "2026-08-06T00:00:00Z"}
        )

    _mock_pooled_client(monkeypatch, handler)
    client = HekbClient(Settings(hekb_url="http://hekb-test:8080"))

    knowledge_object = build_hekb_object(
        {"concept_id": "c1", "normalized_hash": "h1", "invariants": {}, "proof": {}},
        position=[0.1, 0.2],
        session_id="sess-1",
        cycle=3,
    )
    result = await client.store(knowledge_object)

    assert captured["path"] == "/v1/objects"
    assert captured["json"]["kind"] == "OBSERVATION"
    assert captured["json"]["vector"] == [0.1, 0.2]
    assert captured["json"]["labels"]["session_id"] == "sess-1"
    assert captured["json"]["labels"]["cycle"] == "3"
    assert result["object_id"] == "a" * 64


def test_build_hekb_object_maps_lift_response_fields():
    lift_result = {
        "concept_id": "c1",
        "normalized_hash": "h1",
        "invariants": {"betti_0": 1, "betti_1": 0, "betti_2": 0, "euler_characteristic": 1},
        "compression_ratio": 2.5,
        "proof": {"is_valid": True},
    }
    obj = build_hekb_object(lift_result, position=[1.0, 2.0], session_id="sess-1", cycle=7)

    assert obj["kind"] == "OBSERVATION"
    assert obj["vector"] == [1.0, 2.0]
    assert obj["attributes"] == {
        "betti_0": 1.0, "betti_1": 0.0, "betti_2": 0.0,
        "euler_characteristic": 1.0, "compression_ratio": 2.5,
    }
    assert obj["labels"] == {
        "concept_id": "c1", "normalized_hash": "h1",
        "session_id": "sess-1", "cycle": "7", "proof_is_valid": "True",
    }
