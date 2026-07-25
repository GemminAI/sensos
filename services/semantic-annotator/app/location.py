"""Location extraction - parses the `location` slice of the combined
annotation response (see app/tags.py::extract_json_object).

Literal place names only. No coordinates, no lat/lon, no geolocation
grounding - that would be fabrication (an LLM has no way to genuinely
verify a geolocation from text alone) and, more fundamentally, geometry is
the future CTG Engine's responsibility, never this service's.
"""

from __future__ import annotations

from typing import Any


def parse_location(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("location")
    if not isinstance(raw, dict):
        return {"primary": None, "type": None, "normalized": None}

    def _str_or_none(value: Any) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    return {
        "primary": _str_or_none(raw.get("primary")),
        "type": _str_or_none(raw.get("type")),
        "normalized": _str_or_none(raw.get("normalized")),
    }
