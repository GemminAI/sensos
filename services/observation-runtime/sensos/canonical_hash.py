"""
sensos.canonical_hash — SPEC-SENSOS-RTV2-001 v1.4 Contract 1, canonical_tag_hash
==================================================================================

Implements v1.4 Contract 1's ``canonical_tag_hash`` field:

    canonical_tag_hash = SHA-256(JCS(grounded_state))

using ``rfc8785`` (a third-party, spec-conformant implementation of RFC 8785
JSON Canonicalization Scheme — verified against the RFC's own reference test
vectors in ``tests/test_canonical_hash.py``, not hand-rolled here).

Scope, per v1.4 Contract 1's explicit hash-range rule:

- The hash covers ONLY ``grounded_state`` (the discrete-tag structure).
- ``dense_projection.vector`` (the floating-point embedding) MUST NOT enter
  the hash.
- ``attestation`` MUST NOT enter the hash either — it is reproducibility
  metadata about the *projection*, not part of the canonical tag identity.

This is intentionally a NEW, separate module from the two pre-existing,
unrelated hash implementations already in this repo:

- ``services/nvs-runtime/runtime/services/crystallizer.py``'s
  ``crystallize_state_hash()`` — self-described as "JCS-like" but is plain
  ``json.dumps(sort_keys=True)``, not RFC 8785, and hashes a different
  object shape (``{schema_version, subject_origin, narrative, tags}``).
- ``services/observation-runtime/sensos/abi/nvs74/object.py``'s
  ``generate_state_hash()`` — a DJB2-style rolling hash over
  ``{step, metrics}``, unrelated to JCS entirely.

Neither of those is replaced or altered here, per instruction. This module
is the v1.4-Contract-specific implementation; the other two remain
whatever they already are for their own, separate purposes.
"""

from __future__ import annotations

import hashlib
from typing import Any

import rfc8785


def canonical_tag_hash(grounded_state: dict[str, Any]) -> str:
    """
    SHA-256(JCS(grounded_state)), hex-encoded.

    Takes ONLY the ``grounded_state`` sub-object — not a full Contract 1
    envelope. This makes exclusion of ``dense_projection.vector`` and
    ``attestation`` structural rather than a filtering step that could have
    bugs: those fields are never in scope, because they were never passed
    in. See ``canonical_tag_hash_from_envelope`` for the envelope-level
    convenience wrapper that makes this exclusion explicit and testable
    even when the full Contract 1 envelope is what you have on hand.
    """
    canonical_bytes = rfc8785.dumps(grounded_state)
    return hashlib.sha256(canonical_bytes).hexdigest()


def canonical_tag_hash_from_envelope(envelope: dict[str, Any]) -> str:
    """
    Convenience wrapper over a full v1.4 Contract 1 envelope (the shape
    with sibling ``grounded_state`` / ``dense_projection`` keys). Extracts
    and hashes ONLY ``envelope["grounded_state"]`` — ``dense_projection``
    (and therefore its ``vector`` and ``attestation`` sub-fields) is never
    read, regardless of what it contains.

    Raises ValueError if the envelope has no ``grounded_state`` key at all
    — a malformed envelope is not silently hashed as an empty object.
    """
    if "grounded_state" not in envelope:
        raise ValueError("envelope missing required 'grounded_state' key")
    return canonical_tag_hash(envelope["grounded_state"])
