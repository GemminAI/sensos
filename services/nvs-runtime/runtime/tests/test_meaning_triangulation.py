"""Tests for runtime.services.meaning_triangulation — no mocking: real
MeaningMapper/MSR, same convention as test_meaning_trajectory.py.
"""

from __future__ import annotations

from runtime.services.meaning_trajectory import build_hext_observation
from runtime.services.meaning_triangulation import (
    TriangulationInput,
    TriangulationState,
    run_meaning_triangulation,
)


def _observations(text: str, count: int = 8, prefix: str = "obs") -> list[dict]:
    return [
        build_hext_observation(
            observation_id=f"{prefix}-{i:04d}",
            text=text,
            state_hash="a" * 64,
            sealed_at=f"2026-08-18T00:00:{i:02d}Z",
        )
        for i in range(count)
    ]


def test_two_identical_paths_are_deterministic_and_zero_distance():
    """Replaying the exact same content through two independent, fresh
    runs is the "identical input replay" leg — proves determinism, not
    an assumption."""
    text = "the system is stable and observing correctly"
    inputs = [
        TriangulationInput(path_id="path-a", observations=_observations(text, prefix="a"), method="repeated_stable"),
        TriangulationInput(path_id="path-b", observations=_observations(text, prefix="b"), method="replay"),
    ]
    result = run_meaning_triangulation(inputs, triangulation_id="tri-1", divergence_epsilon=1e-9)

    assert len(result.measurements) == 2
    assert all(m.stabilized for m in result.measurements)
    pair = result.pairwise[0]
    assert pair.both_stabilized is True
    assert pair.centroid_distance is not None
    assert pair.centroid_distance < 1e-9  # identical text -> identical theta -> identical centroid
    assert result.state == TriangulationState.STABLE


def test_bootstrap_mode_basin_signal_is_flagged_not_meaningful():
    """Documented limitation, enforced: with no shared field prior, both
    paths stabilize novel (basin_id=None), so same_basin is trivially True
    -- basin_signal_meaningful must say so explicitly."""
    text = "the system is stable and observing correctly"
    inputs = [
        TriangulationInput(path_id="path-a", observations=_observations(text, prefix="a"), method="repeated_stable"),
        TriangulationInput(path_id="path-b", observations=_observations(text, prefix="b"), method="replay"),
    ]
    result = run_meaning_triangulation(inputs, triangulation_id="tri-2", divergence_epsilon=1.0)

    pair = result.pairwise[0]
    assert pair.same_basin is True  # trivially, both None
    assert pair.basin_signal_meaningful is False  # ...and the result says not to trust that


def test_no_divergence_epsilon_is_not_evaluable_even_with_enough_data():
    """This module refuses to invent a default distance cutoff for "the
    same meaning" -- omitting divergence_epsilon must not silently produce
    a verdict."""
    text = "the system is stable and observing correctly"
    inputs = [
        TriangulationInput(path_id="path-a", observations=_observations(text, prefix="a"), method="repeated_stable"),
        TriangulationInput(path_id="path-b", observations=_observations(text, prefix="b"), method="replay"),
    ]
    result = run_meaning_triangulation(inputs, triangulation_id="tri-3")

    assert result.state == TriangulationState.NOT_EVALUABLE
    assert "divergence_epsilon" in result.note


def test_fewer_than_two_stabilized_paths_is_not_evaluable():
    inputs = [
        TriangulationInput(
            path_id="path-a",
            observations=_observations("the system is stable", count=8, prefix="a"),
            method="repeated_stable",
        ),
        TriangulationInput(
            path_id="path-b",
            observations=_observations("too short", count=2, prefix="b"),  # below dwell_steps=5
            method="paraphrase",
        ),
    ]
    result = run_meaning_triangulation(inputs, triangulation_id="tri-4", divergence_epsilon=1.0)

    assert result.measurements[0].stabilized is True
    assert result.measurements[1].stabilized is False
    assert result.state == TriangulationState.NOT_EVALUABLE
    assert "1 of 2" in result.note


def test_different_content_can_diverge_with_a_tight_epsilon():
    """Two genuinely different stable texts, compared with an extremely
    tight caller-supplied epsilon, must not be forced into STABLE."""
    inputs = [
        TriangulationInput(
            path_id="path-a",
            observations=_observations("the system is stable and observing correctly", prefix="a"),
            method="repeated_stable",
        ),
        TriangulationInput(
            path_id="path-b",
            observations=_observations("a completely different sentence about something else", prefix="b"),
            method="paraphrase",
        ),
    ]
    result = run_meaning_triangulation(inputs, triangulation_id="tri-5", divergence_epsilon=1e-12)

    assert result.state == TriangulationState.DIVERGENT


def test_single_path_is_not_evaluable():
    inputs = [
        TriangulationInput(
            path_id="path-a",
            observations=_observations("the system is stable", prefix="a"),
            method="repeated_stable",
        )
    ]
    result = run_meaning_triangulation(inputs, triangulation_id="tri-6", divergence_epsilon=1.0)
    assert result.pairwise == ()
    assert result.state == TriangulationState.NOT_EVALUABLE


def test_empty_input_is_not_evaluable():
    result = run_meaning_triangulation([], triangulation_id="tri-7", divergence_epsilon=1.0)
    assert result.measurements == ()
    assert result.state == TriangulationState.NOT_EVALUABLE
