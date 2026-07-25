"""Experimental-validation analogs of Gen2 CTS tests.

- CTS-ENH-001 (Firewall Enforce, RFC-NVS-0001 5.2) -> test_firewall_blocks_path_entering_restricted_ids
- CTS-ENT-001 (Attestation Shake, RFC-NVS-0001 5.3) -> test_trust_manifest_round_trip (SIMULATED — no TPM, see security.py docstring)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hekb_mcp.security import (
    CAP_SYS_NAVIGATE,
    CAP_SYS_OBSERVE,
    CapabilityDenied,
    MeaningFirewallBlocked,
    ObservationTokenIssuer,
    TrustManifestIssuer,
    check_geodesic_boundary,
    enforce_geodesic_boundary,
)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "auth.yaml"


@pytest.fixture()
def token_issuer() -> ObservationTokenIssuer:
    return ObservationTokenIssuer(config_path=CONFIG_PATH)


def test_issue_and_verify_round_trip(token_issuer: ObservationTokenIssuer):
    token = token_issuer.issue("test-subject", capabilities=CAP_SYS_OBSERVE | CAP_SYS_NAVIGATE)

    claims = token_issuer.verify(token)

    assert claims.subject == "test-subject"
    assert claims.has_capability(CAP_SYS_OBSERVE)
    assert claims.has_capability(CAP_SYS_NAVIGATE)


def test_capability_not_granted_is_denied(token_issuer: ObservationTokenIssuer):
    token = token_issuer.issue("observer-only", capabilities=CAP_SYS_OBSERVE)
    claims = token_issuer.verify(token)

    with pytest.raises(CapabilityDenied):
        claims.require(CAP_SYS_NAVIGATE)


def test_tampered_token_fails_verification(token_issuer: ObservationTokenIssuer):
    token = token_issuer.issue("test-subject", capabilities=CAP_SYS_OBSERVE)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(ValueError):
        token_issuer.verify(tampered)


# --- Meaning Firewall (graph-membership approximation) --------------------


def test_firewall_allows_clean_path():
    result = check_geodesic_boundary(path=[1, 2, 3], restricted_object_ids=frozenset({99}))
    assert result.blocked is False
    assert result.blocked_object_ids == []


def test_firewall_blocks_path_entering_restricted_ids():
    result = check_geodesic_boundary(path=[1, 2, 99], restricted_object_ids=frozenset({99}))
    assert result.blocked is True
    assert result.blocked_object_ids == [99]


def test_enforce_geodesic_boundary_raises_with_ns_err_firewall_block_code():
    with pytest.raises(MeaningFirewallBlocked) as exc_info:
        enforce_geodesic_boundary(path=[1, 99, 3], restricted_object_ids=frozenset({99}))
    assert exc_info.value.code == "NVS_ERR_FIREWALL_BLOCK"
    assert exc_info.value.blocked_object_ids == [99]


# --- TrustManifest (software simulation) -----------------------------------


def test_trust_manifest_round_trip():
    issuer = TrustManifestIssuer(config_path=CONFIG_PATH)

    manifest = issuer.issue(nonce="deadbeefcafebabe", semantic_compliance_mask=0x01)

    assert manifest.manifest_magic == "SOST"
    assert manifest.nonce_feedback == "deadbeefcafebabe"
    assert manifest.sbom_hash == "NOT_AVAILABLE_SOFTWARE_SIMULATION"
    assert manifest.tpm_pcr_quote == "NOT_AVAILABLE_SOFTWARE_SIMULATION"
    assert issuer.verify(manifest) is True


def test_trust_manifest_tampered_signature_fails_verification():
    issuer = TrustManifestIssuer(config_path=CONFIG_PATH)
    manifest = issuer.issue(nonce="abc123")
    manifest.signature = manifest.signature[:-1] + ("A" if manifest.signature[-1] != "A" else "B")

    assert issuer.verify(manifest) is False
