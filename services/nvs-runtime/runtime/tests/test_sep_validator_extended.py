import pytest

from runtime.core.exceptions import ValidationError
from runtime.models.enums import SCHEMA_VERSION, SEP_VERSION
from runtime.validators.sep_validator import (
    validate_l1_envelope,
    validate_l3_sep_event_type,
    validate_l5_payload,
    validate_sep_event,
)


def test_l1_missing_fields():
    with pytest.raises(ValidationError) as exc:
        validate_l1_envelope({"schema_version": SCHEMA_VERSION})
    assert "ENVELOPE" in exc.value.code


def test_l3_all_allowed_types():
    for t in [
        "excitation.pulse",
        "excitation.sweep",
        "excitation.chirp",
        "disturbance.external",
        "disturbance.noise",
        "disturbance.shock",
        "control.correction",
        "control.inhibit",
        "input.raw",
    ]:
        validate_l3_sep_event_type(t)


def test_l5_disturbance_and_input_raw():
    validate_l5_payload("disturbance.noise", {"source": "environment"})
    validate_l5_payload("input.raw", {"content": "hello"})


def test_valid_sep_raw():
    env = {
        "schema_version": SCHEMA_VERSION,
        "event_id": "550e8400-e29b-41d4-a716-446655440000",
        "event_type": "sep.raw",
        "session_id": "550e8400-e29b-41d4-a716-446655440001",
        "agent_id": "550e8400-e29b-41d4-a716-446655440002",
        "source_provider": "custom",
        "timestamp": "2026-06-14T12:00:00.000Z",
        "payload": {
            "sep_version": SEP_VERSION,
            "event_id": "550e8400-e29b-41d4-a716-446655440003",
            "event_type": "input.raw",
            "timestamp": "2026-06-14T12:00:00.000Z",
            "payload": {"content": "unclassified"},
        },
    }
    assert validate_sep_event(env) == "input.raw"
