"""Subject extraction - parses the `subject` slice of the combined
annotation response (see app/tags.py::extract_json_object)."""

from __future__ import annotations

from typing import Any


def parse_subject(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("subject")
    if not isinstance(raw, dict):
        return {"primary": None, "type": None, "description": None}

    def _str_or_none(value: Any) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    return {
        "primary": _str_or_none(raw.get("primary")),
        "type": _str_or_none(raw.get("type")),
        "description": _str_or_none(raw.get("description")),
    }
