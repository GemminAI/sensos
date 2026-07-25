"""Experimental-validation analog of CTS-CORE-002 (Geodesic Check) end-to-end
through the tool layer, plus capability/firewall enforcement at the tool boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from hekb_mcp.client import HekbRuntimeClient
from hekb_mcp.security import CAP_SYS_NAVIGATE, CAP_SYS_OBSERVE, ObservationTokenIssuer, TrustManifestIssuer
from hekb_mcp.tests.fake_hekb_runtime import FakeHekbRuntime
from hekb_mcp.tools import ToolContext, call_tool

CONFIG_PATH = Path(__file__).parent.parent / "config" / "auth.yaml"


@pytest.fixture()
def token_issuer() -> ObservationTokenIssuer:
    return ObservationTokenIssuer(config_path=CONFIG_PATH)


def make_ctx(fake: FakeHekbRuntime, token_issuer: ObservationTokenIssuer, restricted: frozenset[int] = frozenset()) -> ToolContext:
    client = HekbRuntimeClient(base_url="http://test", transport=fake.transport())
    return ToolContext(
        client=client,
        token_issuer=token_issuer,
        trust_issuer=TrustManifestIssuer(config_path=CONFIG_PATH),
        restricted_object_ids=restricted,
    )


def test_get_object_returns_object_fields(token_issuer: ObservationTokenIssuer):
    fake = FakeHekbRuntime()
    fake.seed_object(1, label="Yahweh", curvature=0.9)
    ctx = make_ctx(fake, token_issuer)
    token = token_issuer.issue("caller", capabilities=CAP_SYS_OBSERVE)

    result = call_tool("get_object", {"object_id": 1, "token": token}, ctx)

    assert result["label"] == "Yahweh"
    assert result["curvature"] == 0.9


def test_get_object_without_capability_is_denied(token_issuer: ObservationTokenIssuer):
    fake = FakeHekbRuntime()
    fake.seed_object(1, label="Yahweh")
    ctx = make_ctx(fake, token_issuer)
    token = token_issuer.issue("caller", capabilities=0)  # no capabilities granted

    result = call_tool("get_object", {"object_id": 1, "token": token}, ctx)

    assert result["error"] == "NVS_ERR_CAPABILITY_DENIED"


def test_observe_without_engine_configured_returns_error(token_issuer: ObservationTokenIssuer):
    fake = FakeHekbRuntime()
    ctx = make_ctx(fake, token_issuer)  # observation_engine defaults to None
    token = token_issuer.issue("caller", capabilities=CAP_SYS_OBSERVE)

    result = call_tool("observe", {"text": "hello", "token": token}, ctx)

    assert result["error"] == "NVS_ERR_ENGINE_UNAVAILABLE"


def test_follow_geodesic_returns_path_when_clean(token_issuer: ObservationTokenIssuer):
    fake = FakeHekbRuntime()
    fake.seed_geodesic(1, 2, found=True, total_cost=2.0, path=[1, 2])
    ctx = make_ctx(fake, token_issuer, restricted=frozenset({99}))
    token = token_issuer.issue("caller", capabilities=CAP_SYS_NAVIGATE)

    result = call_tool("follow_geodesic", {"from_object_id": 1, "to_object_id": 2, "token": token}, ctx)

    assert result["found"] is True
    assert result["path"] == [1, 2]


def test_follow_geodesic_blocked_by_meaning_firewall(token_issuer: ObservationTokenIssuer):
    fake = FakeHekbRuntime()
    fake.seed_geodesic(1, 3, found=True, total_cost=4.0, path=[1, 99, 3])
    ctx = make_ctx(fake, token_issuer, restricted=frozenset({99}))
    token = token_issuer.issue("caller", capabilities=CAP_SYS_NAVIGATE)

    result = call_tool("follow_geodesic", {"from_object_id": 1, "to_object_id": 3, "token": token}, ctx)

    assert result["error"] == "NVS_ERR_FIREWALL_BLOCK"
    assert result["blocked_object_ids"] == [99]


def test_resolve_attractor_is_explicit_not_implemented(token_issuer: ObservationTokenIssuer):
    fake = FakeHekbRuntime()
    ctx = make_ctx(fake, token_issuer)

    result = call_tool("resolve_attractor", {}, ctx)

    assert result["status"] == "NOT_IMPLEMENTED"
    assert "no attractor-ranking primitive" in result["reason"]


def test_find_pullback_is_explicit_not_implemented(token_issuer: ObservationTokenIssuer):
    fake = FakeHekbRuntime()
    ctx = make_ctx(fake, token_issuer)

    result = call_tool("find_pullback", {}, ctx)

    assert result["status"] == "NOT_IMPLEMENTED"
    assert "pullback/pushout" in result["reason"]


def test_get_trust_manifest_returns_simulated_manifest(token_issuer: ObservationTokenIssuer):
    fake = FakeHekbRuntime()
    ctx = make_ctx(fake, token_issuer)

    result = call_tool("get_trust_manifest", {"nonce": "abc123"}, ctx)

    assert result["manifest_magic"] == "SOST"
    assert result["nonce_feedback"] == "abc123"
    assert result["tpm_pcr_quote"] == "NOT_AVAILABLE_SOFTWARE_SIMULATION"
