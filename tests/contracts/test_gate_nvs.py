"""gate_nvs.check_nvs_payload: hidden-trajectory goes to its own checker, everything else to gate.check_payload."""

from __future__ import annotations

import json
from typing import Any

import pytest
from contracts import gate, gate_nvs
from contracts.gate_nvs import check_nvs_payload
from contracts.hidden_trajectory import HiddenTrajectoryResult
from contracts.schemas import CONTRACTS_DIR
from test_hidden_trajectory import BLOBS, MLP, envelope_of, payload_of

MSR = CONTRACTS_DIR / "msr/vectors"
WINDOW = json.loads((MSR / "window-rows.json").read_text(encoding="utf-8"))
WINDOW_BLOBS = {u: bytes.fromhex(h) for u, h in WINDOW["blobs"].items()}
EXPONENT = json.loads((MSR / "calibration-exponent.json").read_text(encoding="utf-8"))[
    "cases"
]
SERIES = json.loads((MSR / "series.json").read_text(encoding="utf-8"))["cases"]


def _window(case: dict[str, Any]) -> tuple[Any, ...]:
    return case["envelope"], case["stored"], WINDOW_BLOBS


@pytest.mark.parametrize(
    "case", WINDOW["cases"], ids=[c["id"] for c in WINDOW["cases"]]
)
def test_a_msr_window_gives_exactly_what_gate_check_payload_gives(
    case: dict[str, Any],
) -> None:
    envelope, stored, blobs = _window(case)
    assert check_nvs_payload(envelope, stored, blobs) == gate.check_payload(
        envelope, stored, blobs
    )


@pytest.mark.parametrize("case", EXPONENT, ids=[c["id"] for c in EXPONENT])
def test_msr_calibration_gives_exactly_what_gate_check_payload_gives(
    case: dict[str, Any],
) -> None:
    envelope = {
        "payload_schema": case["payload_schema"],
        "payload": case["payload"],
        "parents": [],
    }
    found = check_nvs_payload(envelope)
    assert isinstance(found, list) and found == gate.check_payload(envelope)


@pytest.mark.parametrize("case", SERIES, ids=[c["id"] for c in SERIES])
def test_msr_series_gives_exactly_what_gate_check_payload_gives(
    case: dict[str, Any],
) -> None:
    envelope = {
        "payload_schema": {"id": "msr.geometry-measurement", "version": "0.7.1"},
        "payload": case["payload"],
        "parents": case["parents"],
    }
    blobs = {u: bytes.fromhex(h) for u, h in case["blobs"].items()}
    assert check_nvs_payload(envelope, None, blobs) == gate.check_payload(
        envelope, None, blobs
    )


def test_the_arguments_reach_gate_check_payload_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[Any, ...]] = []

    def spy(
        envelope: Any,
        stored: Any = None,
        blobs: Any = None,
        parent_contents: Any = None,
    ) -> list[Any]:
        seen.append((envelope, stored, blobs, parent_contents))
        return ["sentinel"]

    monkeypatch.setattr(gate, "check_payload", spy)
    envelope = {
        "payload_schema": {"id": "msr.calibration", "version": "0.8.0"},
        "payload": {},
    }
    found: Any = check_nvs_payload(envelope, {"a": 1}, {"u": b"x"}, {"p": "c"})
    assert found == ["sentinel"]
    assert seen == [(envelope, {"a": 1}, {"u": b"x"}, {"p": "c"})]


def test_hidden_trajectory_never_calls_gate_check_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError(
            "gate.check_payload must not be called for nvs.hidden-trajectory"
        )

    monkeypatch.setattr(gate, "check_payload", boom)
    for version in ("0.1.0", "0.2.0", "0.1.0-draft"):
        envelope = envelope_of(
            payload_of(MLP),
            payload_schema={"id": "nvs.hidden-trajectory", "version": version},
        )
        assert isinstance(
            check_nvs_payload(envelope, None, BLOBS), HiddenTrajectoryResult
        )


def test_hidden_trajectory_returns_its_own_result_type() -> None:
    result = check_nvs_payload(envelope_of(payload_of(MLP)), None, BLOBS)
    assert isinstance(result, HiddenTrajectoryResult) and result.ok
    assert [u.check for u in result.unverifiable] == ["contract_binding"]


@pytest.mark.parametrize("version", ["0.2.0", "0.1.0-draft", "0.1", ""])
def test_t_u5_19_another_version_is_s39(version: str) -> None:
    envelope = envelope_of(
        payload_of(MLP),
        payload_schema={"id": "nvs.hidden-trajectory", "version": version},
    )
    result = check_nvs_payload(envelope, None, BLOBS)
    assert isinstance(result, HiddenTrajectoryResult)
    assert [(v.code, v.message) for v in result.violations] == [
        ("S39", f"unknown payload_schema nvs.hidden-trajectory {version}")
    ]
    assert result.unverifiable == ()


def test_an_unknown_id_is_s39_as_before() -> None:
    envelope = {
        "payload_schema": {"id": "nvs.unknown-thing", "version": "0.1.0"},
        "payload": {},
        "parents": [],
    }
    found = check_nvs_payload(envelope)
    assert isinstance(found, list) and [v.code for v in found] == ["S39"]
    assert found == gate.check_payload(envelope)


def test_gate_payload_schemas_has_no_hidden_trajectory() -> None:
    assert all(ident != "nvs.hidden-trajectory" for ident, _ in gate.PAYLOAD_SCHEMAS)
    assert gate_nvs.check_nvs_payload is check_nvs_payload
    # and calling the old entry with a hidden-trajectory envelope is still S39 (gate.py was not extended)
    old = gate.check_payload(envelope_of(payload_of(MLP)), None, BLOBS)
    assert [v.code for v in old] == ["S39"]


@pytest.mark.parametrize(
    "case", WINDOW["cases"][:3], ids=[c["id"] for c in WINDOW["cases"][:3]]
)
def test_contract_facts_is_ignored_by_the_msr_delegation(case: dict[str, Any]) -> None:
    envelope, stored, blobs = _window(case)
    assert check_nvs_payload(
        envelope, stored, blobs, contract_facts={"anything": "not even valid"}
    ) == gate.check_payload(envelope, stored, blobs)


def test_contract_facts_reaches_the_hidden_trajectory_checker() -> None:
    with pytest.raises(Exception, match="gate_internal_error"):
        check_nvs_payload(envelope_of(payload_of(MLP)), None, BLOBS, contract_facts={})
