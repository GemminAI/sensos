"""
Tests for sensos.evidence_accounting (SPEC-SENSOS-RTV2-001 v1.4 Section
7.4 G3). All ObservationState sequences below are synthetic — no real
38-Port evaluation has occurred.
"""

from __future__ import annotations

import dataclasses

import pytest
from sensos.evidence_accounting import (
    tally_observation_states,
)
from sensos.observation_state import ObservationState


def test_basic_tally_counts_correctly():
    states = [
        ObservationState.INDIVIDUALLY_IDENTIFIABLE,
        ObservationState.INDIVIDUALLY_IDENTIFIABLE,
        ObservationState.CLASS_IDENTIFIABLE,
        ObservationState.NOT_IDENTIFIABLE,
        ObservationState.NOT_EVALUABLE,
        ObservationState.BLOCKED,
    ]
    accounting = tally_observation_states(states)
    assert accounting.total == 6
    assert accounting.count(ObservationState.INDIVIDUALLY_IDENTIFIABLE) == 2
    assert accounting.count(ObservationState.CLASS_IDENTIFIABLE) == 1
    assert accounting.count(ObservationState.NOT_IDENTIFIABLE) == 1
    assert accounting.count(ObservationState.NOT_EVALUABLE) == 1
    assert accounting.count(ObservationState.BLOCKED) == 1


def test_all_five_states_present_even_when_zero():
    states = [ObservationState.BLOCKED] * 3
    accounting = tally_observation_states(states)
    assert set(accounting.counts.keys()) == set(ObservationState)
    assert accounting.count(ObservationState.INDIVIDUALLY_IDENTIFIABLE) == 0


def test_denominator_is_always_full_total_not_filtered():
    # v1.4 Section 7.2: BLOCKED/NOT_EVALUABLE/NOT_IDENTIFIABLE must not be
    # excluded from the denominator used for any rate.
    states = (
        [ObservationState.INDIVIDUALLY_IDENTIFIABLE] * 2
        + [ObservationState.BLOCKED] * 5
        + [ObservationState.NOT_EVALUABLE] * 3
    )
    accounting = tally_observation_states(states)
    assert accounting.total == 10  # not 2 (the "successful" subset)
    assert accounting.rate(ObservationState.INDIVIDUALLY_IDENTIFIABLE) == pytest.approx(0.2)
    assert accounting.rate(ObservationState.BLOCKED) == pytest.approx(0.5)


def test_as_fractions_always_pairs_numerator_with_denominator():
    states = [ObservationState.CLASS_IDENTIFIABLE] * 4 + [ObservationState.BLOCKED] * 6
    accounting = tally_observation_states(states)
    fractions = accounting.as_fractions()
    assert fractions[ObservationState.CLASS_IDENTIFIABLE] == (4, 10)
    assert fractions[ObservationState.BLOCKED] == (6, 10)
    assert fractions[ObservationState.NOT_IDENTIFIABLE] == (0, 10)
    # every entry carries the SAME denominator -- it's never silently
    # dropped or replaced with a filtered subtotal.
    assert {denom for _num, denom in fractions.values()} == {10}


def test_rates_sum_to_one():
    states = (
        [ObservationState.INDIVIDUALLY_IDENTIFIABLE] * 3
        + [ObservationState.CLASS_IDENTIFIABLE] * 2
        + [ObservationState.NOT_IDENTIFIABLE] * 1
        + [ObservationState.NOT_EVALUABLE] * 4
        + [ObservationState.BLOCKED] * 5
    )
    accounting = tally_observation_states(states)
    total_rate = sum(accounting.rate(s) for s in ObservationState)
    assert total_rate == pytest.approx(1.0)


def test_empty_states_raises():
    with pytest.raises(ValueError, match="empty"):
        tally_observation_states([])


def test_non_observation_state_element_raises():
    with pytest.raises(TypeError, match="ObservationState"):
        tally_observation_states([ObservationState.BLOCKED, "not_a_state"])  # type: ignore[list-item]


def test_accounting_is_immutable():
    accounting = tally_observation_states([ObservationState.BLOCKED])
    with pytest.raises(dataclasses.FrozenInstanceError):
        accounting.total = 100  # type: ignore[misc]


def test_single_state_full_representation():
    accounting = tally_observation_states([ObservationState.INDIVIDUALLY_IDENTIFIABLE] * 38)
    assert accounting.total == 38
    assert accounting.rate(ObservationState.INDIVIDUALLY_IDENTIFIABLE) == pytest.approx(1.0)
