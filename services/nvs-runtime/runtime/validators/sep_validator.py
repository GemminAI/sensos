"""RFC-NVS16 SEP validator — 5-stage validation per RFC-NVS42 v0.3 §5.3."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from runtime.core.exceptions import ValidationError
from runtime.models.enums import (
    SCHEMA_VERSION,
    SEP_EVENT_TYPES,
    SEP_PREFIX_MAP,
    SEP_VERSION,
    RuntimeEventType,
)

ENVELOPE_REQUIRED = frozenset({
    "schema_version",
    "event_id",
    "event_type",
    "session_id",
    "agent_id",
    "source_provider",
    "timestamp",
    "payload",
})

SEP_WRAPPER_REQUIRED = frozenset({
    "sep_version",
    "event_id",
    "event_type",
    "timestamp",
    "payload",
})

SEP_EVENT_TYPES_REQUIRING_VALIDATION = frozenset({
    RuntimeEventType.SEP_EXCITATION.value,
    RuntimeEventType.SEP_DISTURBANCE.value,
    RuntimeEventType.SEP_CONTROL.value,
    RuntimeEventType.SEP_RAW.value,
})


def _require_fields(data: dict[str, Any], fields: frozenset[str], stage: str) -> None:
    missing = [f for f in fields if f not in data or data[f] is None]
    if missing:
        raise ValidationError(
            f"ERROR_{stage}_MISSING_FIELDS",
            f"Missing required fields at {stage}: {', '.join(missing)}",
        )


def _validate_uuid(value: Any, field: str) -> None:
    try:
        UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise ValidationError("ERROR_INVALID_UUID", f"Invalid UUID for {field}") from exc


def validate_l1_envelope(envelope: dict[str, Any]) -> None:
    _require_fields(envelope, ENVELOPE_REQUIRED, "ENVELOPE")
    if envelope["schema_version"] != SCHEMA_VERSION:
        raise ValidationError(
            "ERROR_INVALID_SCHEMA_VERSION",
            f"Expected {SCHEMA_VERSION}, got {envelope['schema_version']}",
        )
    _validate_uuid(envelope["event_id"], "event_id")
    _validate_uuid(envelope["session_id"], "session_id")
    _validate_uuid(envelope["agent_id"], "agent_id")
    if envelope.get("parent_event_id") is not None:
        _validate_uuid(envelope["parent_event_id"], "parent_event_id")
    if envelope.get("experiment_id") is not None:
        _validate_uuid(envelope["experiment_id"], "experiment_id")


def validate_l2_sep_wrapper(sep_payload: dict[str, Any]) -> None:
    _require_fields(sep_payload, SEP_WRAPPER_REQUIRED, "SEP_WRAPPER")
    if sep_payload["sep_version"] != SEP_VERSION:
        raise ValidationError(
            "ERROR_INVALID_SEP_VERSION",
            f"Expected {SEP_VERSION}, got {sep_payload['sep_version']}",
        )
    _validate_uuid(sep_payload["event_id"], "sep.event_id")


def validate_l3_sep_event_type(sep_event_type: str) -> None:
    if sep_event_type not in SEP_EVENT_TYPES:
        raise ValidationError(
            "ERROR_INVALID_SEP_EVENT",
            f"SEP event_type '{sep_event_type}' is not in RFC-NVS16 §3.2 enumeration",
        )


def validate_l4_prefix_map(runtime_event_type: str, sep_event_type: str) -> None:
    expected = SEP_PREFIX_MAP.get(runtime_event_type)
    if expected is None:
        return
    if expected == "input.raw":
        if sep_event_type != "input.raw":
            raise ValidationError(
                "ERROR_SEP_PREFIX_MISMATCH",
                f"Runtime {runtime_event_type} requires SEP input.raw, got {sep_event_type}",
            )
        return
    if not sep_event_type.startswith(expected):
        raise ValidationError(
            "ERROR_SEP_PREFIX_MISMATCH",
            f"Runtime {runtime_event_type} requires SEP prefix {expected}*, got {sep_event_type}",
        )


def validate_l5_payload(sep_event_type: str, payload: dict[str, Any]) -> None:
    if sep_event_type.startswith("excitation."):
        if "amplitude" not in payload:
            raise ValidationError("ERROR_SEP_PAYLOAD", "excitation payload requires amplitude")
        amp = payload["amplitude"]
        if not isinstance(amp, (int, float)) or not (0.0 <= float(amp) <= 1.0):
            raise ValidationError("ERROR_SEP_PAYLOAD", "amplitude must be float in [0, 1]")
    elif sep_event_type.startswith("disturbance."):
        if "source" not in payload:
            raise ValidationError("ERROR_SEP_PAYLOAD", "disturbance payload requires source")
    elif sep_event_type.startswith("control."):
        if "target_state" not in payload:
            raise ValidationError("ERROR_SEP_PAYLOAD", "control payload requires target_state")
        if "target_basis" not in payload:
            raise ValidationError("ERROR_SEP_PAYLOAD", "control payload requires target_basis")
        if "authority" not in payload:
            raise ValidationError("ERROR_SEP_PAYLOAD", "control payload requires authority")
    elif sep_event_type == "input.raw":
        if "content" not in payload:
            raise ValidationError("ERROR_SEP_PAYLOAD", "input.raw payload requires content")


def validate_sep_event(envelope: dict[str, Any]) -> str | None:
    """Run full 5-stage validation. Returns inner sep_event_type or None."""
    validate_l1_envelope(envelope)
    event_type = envelope["event_type"]
    if event_type not in SEP_EVENT_TYPES_REQUIRING_VALIDATION:
        return None

    sep_payload = envelope.get("payload")
    if not isinstance(sep_payload, dict):
        raise ValidationError("ERROR_SEP_WRAPPER", "SEP events require object payload")

    validate_l2_sep_wrapper(sep_payload)
    sep_event_type = sep_payload["event_type"]
    validate_l3_sep_event_type(sep_event_type)
    validate_l4_prefix_map(event_type, sep_event_type)
    inner = sep_payload.get("payload", {})
    if not isinstance(inner, dict):
        raise ValidationError("ERROR_SEP_PAYLOAD", "SEP inner payload must be object")
    validate_l5_payload(sep_event_type, inner)
    return sep_event_type
