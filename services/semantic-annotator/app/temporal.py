"""Time extraction - parses the `time` slice of the combined annotation
response (see app/tags.py::extract_json_object).

Named `temporal.py`, not `time.py`, so it never shadows the stdlib `time`
module for anything else in this package that does a bare `import time`.
"""

from __future__ import annotations

from typing import Any

_TENSES = ("past", "present", "future")


def parse_time(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("time")
    if not isinstance(raw, dict):
        return {"absolute": None, "relative": None, "tense": None}

    def _str_or_none(value: Any) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    tense = raw.get("tense")
    return {
        "absolute": _str_or_none(raw.get("absolute")),
        "relative": _str_or_none(raw.get("relative")),
        "tense": tense if tense in _TENSES else None,
    }
