"""Entity extraction - parses the `entities` slice of the combined
annotation response (see app/tags.py::extract_json_object)."""

from __future__ import annotations

from typing import Any


def parse_entities(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("entities")
    if not isinstance(raw, list):
        return []

    entities: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        entity_type = item.get("type")
        if not isinstance(text, str) or not text.strip() or not isinstance(entity_type, str) or not entity_type.strip():
            # No literal span or no type - not a genuine entity, drop it
            # rather than guessing a shape for it.
            continue
        entity: dict[str, Any] = {"text": text.strip(), "type": entity_type.strip()}
        normalized = item.get("normalized")
        if isinstance(normalized, str) and normalized.strip():
            entity["normalized"] = normalized.strip()
        salience = item.get("salience")
        if isinstance(salience, (int, float)):
            entity["salience"] = float(max(0.0, min(1.0, salience)))
        entities.append(entity)
    return entities
