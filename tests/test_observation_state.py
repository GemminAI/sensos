"""Tests for the SPEC-SENSOS-RTV2-001 v1.4 Section 7.2 ObservationState enum."""

from __future__ import annotations

from sensos.dak.decision import DAKDecision
from sensos.observation_state import ObservationState

EXPECTED_MEMBERS = {
    "INDIVIDUALLY_IDENTIFIABLE": "INDIVIDUALLY_IDENTIFIABLE",
    "CLASS_IDENTIFIABLE": "CLASS_IDENTIFIABLE",
    "NOT_IDENTIFIABLE": "NOT_IDENTIFIABLE",
    "NOT_EVALUABLE": "NOT_EVALUABLE",
    "BLOCKED": "BLOCKED",
}


def test_exact_members_and_values():
    actual = {member.name: member.value for member in ObservationState}
    assert actual == EXPECTED_MEMBERS


def test_no_undeclared_members():
    assert len(ObservationState) == 5


def test_members_are_string_valued():
    for member in ObservationState:
        assert isinstance(member.value, str)
        assert member.value == member.name


def test_not_type_confused_with_dak_decision():
    # ObservationState and DAKDecision are separate enums with no shared
    # members, no inheritance relationship, and no cross-comparability.
    assert ObservationState is not DAKDecision
    assert not issubclass(ObservationState, DAKDecision)
    assert not issubclass(DAKDecision, ObservationState)

    dak_values = {member.value for member in DAKDecision}
    obs_values = {member.value for member in ObservationState}
    assert dak_values.isdisjoint(obs_values)

    for obs_member in ObservationState:
        for dak_member in DAKDecision:
            assert obs_member != dak_member


def test_lookup_by_value():
    for member in ObservationState:
        assert ObservationState(member.value) is member
