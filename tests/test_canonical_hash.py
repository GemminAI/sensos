"""
Tests for sensos.canonical_hash (SPEC-SENSOS-RTV2-001 v1.4 Contract 1
canonical_tag_hash = SHA-256(JCS(grounded_state))).

The "known JCS vectors" section below cross-checks against the *official*
RFC 8785 reference test suite (cyberphone/json-canonicalization, maintained
by the RFC's author), fetched into tests/fixtures/jcs_vectors/ — not
hand-constructed by this session. Comparing against externally-authored
reference vectors is what actually substantiates the "RFC 8785 compliant"
claim, rather than only testing self-consistency.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sensos.canonical_hash import canonical_tag_hash, canonical_tag_hash_from_envelope

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jcs_vectors"
VECTOR_NAMES = ["french", "values", "structures", "arrays", "unicode"]


# ---------------------------------------------------------------------------
# Known JCS vectors (official RFC 8785 reference test suite)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", VECTOR_NAMES)
def test_matches_official_rfc8785_reference_vectors(name):
    input_obj = json.loads((FIXTURES / "input" / f"{name}.json").read_text(encoding="utf-8"))
    expected_canonical_bytes = (FIXTURES / "output" / f"{name}.json").read_bytes()
    expected_hash = hashlib.sha256(expected_canonical_bytes).hexdigest()

    # 'arrays' and 'unicode' vectors are top-level arrays/plain-scalar
    # bearing objects; canonical_tag_hash accepts any JSON-serializable
    # value, matching JCS's own generality, even though real Contract 1
    # grounded_state values will always be objects.
    assert canonical_tag_hash(input_obj) == expected_hash


# ---------------------------------------------------------------------------
# Key ordering invariance / determinism
# ---------------------------------------------------------------------------


def test_key_ordering_invariance():
    a = {"subject": "X", "action_core": "Y", "temporal_frame": "Z"}
    b = {"temporal_frame": "Z", "subject": "X", "action_core": "Y"}
    assert canonical_tag_hash(a) == canonical_tag_hash(b)


def test_deterministic_repeat():
    grounded_state = {"subject": "Italian Elderly", "action_core": "Exclude_Alliance"}
    first = canonical_tag_hash(grounded_state)
    second = canonical_tag_hash(dict(grounded_state))
    assert first == second
    assert len(first) == 64  # hex-encoded SHA-256


# ---------------------------------------------------------------------------
# Scope exclusion: dense_projection.vector and attestation
# ---------------------------------------------------------------------------


def _envelope(grounded_state, vector, attestation):
    return {
        "contract_version": "2.0.0",
        "narrative_id": "gmn://nar/test",
        "grounded_state": grounded_state,
        "dense_projection": {"vector": vector, "attestation": attestation},
    }


def test_dense_vector_excluded_from_hash():
    gs = {"subject": "A", "action_core": "B"}
    env1 = _envelope(gs, vector=[0.1, 0.2, 0.3], attestation={"model_id": "m1"})
    env2 = _envelope(gs, vector=[9.9, -9.9, 0.0001], attestation={"model_id": "m1"})
    assert canonical_tag_hash_from_envelope(env1) == canonical_tag_hash_from_envelope(env2)


def test_attestation_excluded_from_hash():
    gs = {"subject": "A", "action_core": "B"}
    env1 = _envelope(gs, vector=[0.1, 0.2], attestation={"model_id": "m1", "precision": "fp16"})
    env2 = _envelope(gs, vector=[0.1, 0.2], attestation={"model_id": "m2", "precision": "fp32"})
    assert canonical_tag_hash_from_envelope(env1) == canonical_tag_hash_from_envelope(env2)


def test_changing_grounded_state_changes_hash():
    env1 = _envelope({"subject": "A"}, vector=[0.1], attestation={})
    env2 = _envelope({"subject": "B"}, vector=[0.1], attestation={})
    assert canonical_tag_hash_from_envelope(env1) != canonical_tag_hash_from_envelope(env2)


def test_envelope_missing_grounded_state_raises():
    with pytest.raises(ValueError, match="grounded_state"):
        canonical_tag_hash_from_envelope({"dense_projection": {"vector": [1.0]}})


# ---------------------------------------------------------------------------
# Unicode / nested structures (additional targeted cases beyond the
# official vectors above)
# ---------------------------------------------------------------------------


def test_unicode_grounded_state():
    gs = {"location_context": "Rome_Street", "subject": "日本人観光客", "note": "héllo"}
    result = canonical_tag_hash(gs)
    assert len(result) == 64
    # order-independence still holds with unicode keys/values present
    gs_reordered = {"subject": "日本人観光客", "note": "héllo", "location_context": "Rome_Street"}
    assert canonical_tag_hash(gs_reordered) == result


def test_nested_grounded_state_structure():
    gs = {
        "subject": "Italian Elderly",
        "temporal_frame": "Future_Counterfactual",
        "tags": {"5w1h": {"who": "X", "what": "Y"}, "list": [1, 2, {"z": 3}]},
    }
    assert canonical_tag_hash(gs) == canonical_tag_hash(gs)  # deterministic on nested input
    assert len(canonical_tag_hash(gs)) == 64
