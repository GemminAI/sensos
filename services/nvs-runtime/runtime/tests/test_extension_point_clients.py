"""CLE/HEKB clients: pooled/retried transport (EXP-Ubuntu011) plus the
Semantic Mapping payload methods `lift()`/`store()` (EXP-Ubuntu012B).
"""

import json

import httpx
from runtime.core.config import Settings
from runtime.gateway import http_pool
from runtime.gateway.cle_client import CLEClient
from runtime.gateway.hekb_client import (
    HekbClient,
    build_hekb_object,
    build_hekb_object_from_port_result,
    build_hekb_object_from_trajectory,
)


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


# ---------------------------------------------------------------------------
# build_hekb_object_from_port_result
# ---------------------------------------------------------------------------

_REAL_P04_RESULT = {
    "port_id": "P04_Port",
    "layer": "CORE",
    "capability": "core_c04_hext_closure_verifier",
    "status": "OK",
    "output_type": "Core.C04.ClosureResult",
    "result": {"quantized_once": [1.0, 2.0, 3.0], "residual": 0.0, "closed": True},
}


def test_build_hekb_object_from_port_result_uses_evidence_kind():
    """EVIDENCE is a real, pre-existing HextKind member (GemminAI/hekb/
    python/hekb/model.py) -- distinct from OBSERVATION, which
    build_hekb_object() already claims for CLE lift results."""
    obj = build_hekb_object_from_port_result("P04", _REAL_P04_RESULT)
    assert obj["kind"] == "EVIDENCE"


def test_build_hekb_object_from_port_result_preserves_port_id():
    obj = build_hekb_object_from_port_result("P17", _REAL_P04_RESULT)
    assert obj["labels"]["port_id"] == "P17"


def test_build_hekb_object_from_port_result_preserves_session_id_when_present():
    obj = build_hekb_object_from_port_result("P02", _REAL_P04_RESULT, session_id="sess-abc")
    assert obj["labels"]["session_id"] == "sess-abc"


def test_build_hekb_object_from_port_result_omits_session_id_when_absent():
    # Stateless Ports (v1.4 Section 5.1) require no session_id at all.
    obj = build_hekb_object_from_port_result("P04", _REAL_P04_RESULT)
    assert "session_id" not in obj["labels"]


def test_build_hekb_object_from_port_result_preserves_cycle_when_present():
    obj = build_hekb_object_from_port_result("P02", _REAL_P04_RESULT, cycle=7)
    assert obj["labels"]["cycle"] == "7"


def test_build_hekb_object_from_port_result_omits_cycle_when_absent():
    obj = build_hekb_object_from_port_result("P04", _REAL_P04_RESULT)
    assert "cycle" not in obj["labels"]


def test_build_hekb_object_from_port_result_preserves_runtime_cycle_id_when_present():
    obj = build_hekb_object_from_port_result(
        "P02", _REAL_P04_RESULT, runtime_cycle_id="9f5a1e2c-0000-0000-0000-000000000001"
    )
    assert obj["labels"]["runtime_cycle_id"] == "9f5a1e2c-0000-0000-0000-000000000001"


def test_build_hekb_object_from_port_result_omits_runtime_cycle_id_when_absent():
    obj = build_hekb_object_from_port_result("P04", _REAL_P04_RESULT)
    assert "runtime_cycle_id" not in obj["labels"]


def test_build_hekb_object_from_port_result_keeps_cycle_and_runtime_cycle_id_distinct():
    # NVS's own integer /observe cycle counter vs the Runtime Decision
    # Boundary's own UUID cycle identity -- two different identities from
    # two different systems, never conflated under one label.
    obj = build_hekb_object_from_port_result(
        "P04", _REAL_P04_RESULT, cycle=7, runtime_cycle_id="9f5a1e2c-0000-0000-0000-000000000001"
    )
    assert obj["labels"]["cycle"] == "7"
    assert obj["labels"]["runtime_cycle_id"] == "9f5a1e2c-0000-0000-0000-000000000001"


def test_build_hekb_object_from_port_result_preserves_raw_result_verbatim():
    obj = build_hekb_object_from_port_result("P04", _REAL_P04_RESULT)
    assert json.loads(obj["labels"]["raw_result"]) == _REAL_P04_RESULT


def test_build_hekb_object_from_port_result_marks_value_kind_measured():
    obj = build_hekb_object_from_port_result("P04", _REAL_P04_RESULT)
    assert obj["labels"]["value_kind"] == "measured"


def test_build_hekb_object_from_port_result_does_not_fabricate_derived_fields():
    """No Var[S]/H_comp/Triad/state_hash computation happens here -- this is
    a raw Port Evidence record, not a v1.4 Canonical Observation (which
    requires EOU data this repo does not have)."""
    obj = build_hekb_object_from_port_result("P04", _REAL_P04_RESULT)
    forbidden_substrings = ("var_s", "h_comp", "state_hash", "canonical", "triad", "eou")
    haystack = json.dumps(obj).lower()
    for term in forbidden_substrings:
        assert term not in haystack, f"unexpected fabricated field marker: {term!r}"
    assert obj["vector"] == []
    assert obj["attributes"] == {}


def test_build_hekb_object_from_port_result_handles_non_json_native_values():
    # Port results can carry nested/heterogeneous types; json.dumps(default=str)
    # must not raise on them.
    weird_result = {"a": {1, 2, 3}, "b": object()}
    obj = build_hekb_object_from_port_result("P04", weird_result)
    assert isinstance(obj["labels"]["raw_result"], str)


# ---------------------------------------------------------------------------
# build_hekb_object_from_trajectory — real StabilizedTrajectory fixture,
# produced by the actual meaning_mapper -> msr chain, not hand-built.
# ---------------------------------------------------------------------------


def _real_trajectory():
    from runtime.services.meaning_trajectory import (
        build_hext_observation,
        run_meaning_trajectory,
    )

    observations = [
        build_hext_observation(
            observation_id=f"fixture-{i:03d}",
            text="a fixed real observation for hekb builder tests",
            state_hash="b" * 64,
            sealed_at=f"2026-08-17T01:00:{i:02d}Z",
        )
        for i in range(8)
    ]
    result = run_meaning_trajectory(observations)
    assert result.trajectory is not None, "fixture setup must actually stabilize"
    return result.trajectory


def test_build_hekb_object_from_trajectory_uses_evidence_kind():
    obj = build_hekb_object_from_trajectory(_real_trajectory())
    assert obj["kind"] == "EVIDENCE"


def test_build_hekb_object_from_trajectory_puts_centroid_in_vector():
    trajectory = _real_trajectory()
    obj = build_hekb_object_from_trajectory(trajectory)
    assert obj["vector"] == list(trajectory.centroid)
    assert len(obj["vector"]) == 8


def test_build_hekb_object_from_trajectory_attributes_are_real_floats():
    trajectory = _real_trajectory()
    obj = build_hekb_object_from_trajectory(trajectory)
    assert obj["attributes"]["dwell_steps"] == float(trajectory.dwell_steps)
    assert obj["attributes"]["dwell_seconds"] == float(trajectory.dwell_seconds)
    assert obj["attributes"]["dimension"] == 8.0


def test_build_hekb_object_from_trajectory_preserves_covariance_and_provenance():
    trajectory = _real_trajectory()
    obj = build_hekb_object_from_trajectory(trajectory)
    assert json.loads(obj["labels"]["covariance"]) == [list(row) for row in trajectory.covariance]
    assert json.loads(obj["labels"]["provenance"]) == list(trajectory.provenance)


def test_build_hekb_object_from_trajectory_preserves_session_and_runtime_cycle_id():
    obj = build_hekb_object_from_trajectory(
        _real_trajectory(), session_id="sess-1", runtime_cycle_id="cycle-1"
    )
    assert obj["labels"]["session_id"] == "sess-1"
    assert obj["labels"]["runtime_cycle_id"] == "cycle-1"


def test_build_hekb_object_from_trajectory_marks_value_kind_measured():
    obj = build_hekb_object_from_trajectory(_real_trajectory())
    assert obj["labels"]["value_kind"] == "measured"


def test_build_hekb_object_from_trajectory_does_not_fabricate_v14_fields():
    obj = build_hekb_object_from_trajectory(_real_trajectory())
    haystack = json.dumps(obj).lower()
    for term in ("var_s", "h_comp", "state_hash", "eou-128", "canonical observation"):
        assert term not in haystack
