"""Confidence calculation - a registry-lite provenance/quality envelope.

This is a deliberately small design, not a port of a full tag-catalog
registry: it inspects only the fields this service actually produces and
classifies each as REAL (the backend genuinely returned it) or PLACEHOLDER
(the backend omitted it - value=None, with a reason). What matters is the
discipline, not a fixed catalog: never emit a confidence-looking number for
something that was not actually extracted. Shared under common/ because the
future CTG Engine consumes this same shape for every Annotation it reads -
see app/schemas.py::ConfidenceBlock.

DERIVED/METADATA/UNAVAILABLE are kept in ConfidenceQuality (app/schemas.py)
for forward compatibility but are unused here - there is no rule-based
enrichment path in v1 (single backend call only), and `metadata` itself is
not confidence-bearing (it's always deterministic, so it isn't a
ConfidenceBlock member at all).
"""

from __future__ import annotations

from typing import Any

_OPTIONAL_TAG_IDS = (
    "T03_predicate_type",
    "T07_actor_role",
    "T08_causality_direction",
    "T11_bias_component",
    "T16_economic_transmission_path",
)
_MANDATORY_TAG_IDS = (
    "T09_strategic_interest_vector",
    "T10_epistemic_confidence",
    "T19_conflict_factuality_index",
)


def _real(value: Any = None) -> dict[str, Any]:
    return {"value": value, "quality": "REAL", "reason": None}


def _placeholder(reason: str) -> dict[str, Any]:
    return {"value": None, "quality": "PLACEHOLDER", "reason": reason}


def _block_entry(parsed_block: dict[str, Any], *, empty_reason: str) -> dict[str, Any]:
    """REAL if at least one field in a subject/time/location-shaped block
    has a genuine (non-None) value, PLACEHOLDER otherwise."""
    if any(v is not None for v in parsed_block.values()):
        return _real()
    return _placeholder(empty_reason)


def build_confidence(
    data: dict[str, Any],
    *,
    tags: dict[str, Any],
    subject: dict[str, Any],
    time: dict[str, Any],
    location: dict[str, Any],
) -> dict[str, Any]:
    tag_entries: dict[str, Any] = {}
    for tag_id in _MANDATORY_TAG_IDS:
        tag_entries[tag_id] = _real(tags.get(tag_id))
    for tag_id in _OPTIONAL_TAG_IDS:
        if tags.get(tag_id) is not None:
            tag_entries[tag_id] = _real(tags.get(tag_id))
        else:
            tag_entries[tag_id] = _placeholder("backend did not return this optional tag")

    entities_present = isinstance(data.get("entities"), list)
    events_present = isinstance(data.get("events"), list)

    return {
        "overall": _real(tags.get("T10_epistemic_confidence")),
        "tags": tag_entries,
        "subject": _block_entry(subject, empty_reason="text has no clear single subject"),
        "entities": _real() if entities_present else _placeholder("backend did not return `entities`"),
        "events": _real() if events_present else _placeholder("backend did not return `events`"),
        "time": _block_entry(time, empty_reason="text carries no genuine temporal information"),
        "location": _block_entry(location, empty_reason="text names no place"),
    }
