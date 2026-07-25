"""ASSERT-05: Expansion Candidate Serialization Conformance (CTS-21.5)."""

from __future__ import annotations

from typing import Any

from hext_stream.schema.base import HextObject

REQUIRED_KEYS = {"type", "candidate_type", "required_node", "generated_node", "processor", "timestamp"}


def extract(published: list[HextObject]) -> list[dict[str, Any]]:
    serialized = []
    for e in published:
        if e.type != "expansion.candidate":
            continue
        envelope = e.to_envelope()
        merged = {
            "type": e.type,
            "candidate_type": e.payload.get("candidate_type"),
            "required_node": e.payload.get("required_node"),
            "generated_node": e.payload.get("generated_node"),
            "processor": e.payload.get("processor"),
            "timestamp": envelope["timestamp"],
        }
        serialized.append(merged)
    return serialized


def verify(serialized_candidate: dict[str, Any], case_id: str) -> tuple[bool, str]:
    """Ported verbatim from CTS-21.md §5 verify_assert_05_expansion_serialization."""
    if not REQUIRED_KEYS.issubset(serialized_candidate.keys()):
        return False, f"[FAIL] ASSERT-05: Missing keys in serialized object for {case_id}"
    if serialized_candidate["type"] != "expansion.candidate":
        return False, f"[FAIL] ASSERT-05: Invalid type for {case_id}"
    return True, "[PASS] ASSERT-05: Expansion candidate serialization verified."
