"""Event extraction - parses the `events` slice of the combined annotation
response (see app/tags.py::extract_json_object)."""

from __future__ import annotations

from typing import Any


def parse_events(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("events")
    if not isinstance(raw, list):
        return []

    events: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        predicate = item.get("predicate")
        if not isinstance(predicate, str) or not predicate.strip():
            continue
        participants_raw = item.get("participants", [])
        participants = (
            [p.strip() for p in participants_raw if isinstance(p, str) and p.strip()]
            if isinstance(participants_raw, list)
            else []
        )
        event: dict[str, Any] = {"predicate": predicate.strip(), "participants": participants}
        predicate_type = item.get("predicate_type")
        if isinstance(predicate_type, str) and predicate_type.strip():
            event["predicate_type"] = predicate_type.strip()
        events.append(event)
    return events
