import pytest

from runtime.core.exceptions import ValidationError
from runtime.models.enums import SCHEMA_VERSION, SEP_VERSION
from runtime.validators.sep_validator import validate_sep_event


def _base_envelope(**overrides):
    data = {
        "schema_version": SCHEMA_VERSION,
        "event_id": "550e8400-e29b-41d4-a716-446655440000",
        "event_type": "sep.excitation",
        "session_id": "550e8400-e29b-41d4-a716-446655440001",
        "agent_id": "550e8400-e29b-41d4-a716-446655440002",
        "source_provider": "anthropic",
        "timestamp": "2026-06-14T12:00:00.000Z",
        "payload": {
            "sep_version": SEP_VERSION,
            "event_id": "550e8400-e29b-41d4-a716-446655440003",
            "event_type": "excitation.step",
            "timestamp": "2026-06-14T12:00:00.000Z",
            "payload": {"amplitude": 0.5, "basis": "35TAG"},
        },
    }
    data.update(overrides)
    return data


def test_valid_excitation_step():
    sep_type = validate_sep_event(_base_envelope())
    assert sep_type == "excitation.step"


def test_reject_invalid_sep_type():
    env = _base_envelope()
    env["payload"]["event_type"] = "disturbance.inject"
    with pytest.raises(ValidationError) as exc:
        validate_sep_event(env)
    assert exc.value.code == "ERROR_INVALID_SEP_EVENT"


def test_reject_prefix_mismatch():
    env = _base_envelope(event_type="sep.disturbance")
    with pytest.raises(ValidationError) as exc:
        validate_sep_event(env)
    assert exc.value.code == "ERROR_SEP_PREFIX_MISMATCH"


def test_valid_control_setpoint():
    env = _base_envelope(
        event_type="sep.control",
        payload={
            "sep_version": SEP_VERSION,
            "event_id": "550e8400-e29b-41d4-a716-446655440003",
            "event_type": "control.setpoint",
            "timestamp": "2026-06-14T12:00:00.000Z",
            "payload": {
                "target_state": [0.1, 0.2],
                "target_basis": "35TAG",
                "authority": "ControlExtension",
            },
        },
    )
    assert validate_sep_event(env) == "control.setpoint"


def test_reject_missing_amplitude():
    env = _base_envelope()
    env["payload"]["payload"] = {"basis": "35TAG"}
    with pytest.raises(ValidationError) as exc:
        validate_sep_event(env)
    assert exc.value.code == "ERROR_SEP_PAYLOAD"


def test_non_sep_event_skips_inner_validation():
    env = _base_envelope(event_type="heartbeat", payload={"status": "ok"})
    assert validate_sep_event(env) is None
