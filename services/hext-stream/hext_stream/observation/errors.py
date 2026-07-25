"""Error codes for RFC-HEXT013 Observation Runtime (§3 Rule 2, §7 Rule 1)."""

from __future__ import annotations


class ObservationRuntimeError(Exception):
    """Base class for RFC-HEXT013 Observation Runtime errors."""

    code: str = "OBS_ERR_UNKNOWN"


class SchemaMismatchError(ObservationRuntimeError):
    """RFC-HEXT013 §3 Rule 2 — raw payload failed type-directed conversion."""

    code = "OBS_ERR_SCHEMA_MISMATCH"


class UngroundedError(ObservationRuntimeError):
    """RFC-HEXT013 §7 Rule 1 — object fails the Observation Directional Constraint."""

    code = "OBS_ERR_UNGROUNDED"
