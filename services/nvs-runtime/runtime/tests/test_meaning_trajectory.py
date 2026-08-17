"""Tests for runtime.services.meaning_trajectory — the real
MeaningMapper -> meaning-space-runtime -> Trajectory chain.

No mocking here: `meaning_mapper` and `msr` do no I/O (confirmed in the
Reality Audit), so exercising them directly with real HEXT Observations
IS the real code path, not a substitute for it.
"""

from __future__ import annotations

from runtime.services.meaning_trajectory import (
    TrajectoryRunResult,
    build_hext_observation,
    run_meaning_trajectory,
)

_STABLE_TEXT = "the system is stable and observing correctly"


def _observation(i: int, text: str = _STABLE_TEXT) -> dict:
    return build_hext_observation(
        observation_id=f"obs-{i:04d}",
        text=text,
        state_hash="a" * 64,
        sealed_at=f"2026-08-17T00:00:{i:02d}Z",
    )


# ---------------------------------------------------------------------------
# build_hext_observation — real wire-schema construction
# ---------------------------------------------------------------------------


def test_build_hext_observation_matches_real_schema():
    obs = build_hext_observation("obs-1", "hello world", "a" * 64, "2026-08-17T00:00:00Z")
    assert obs["object"]["id"] == "obs-1"
    assert obs["evidence"]["body"] == "hello world"
    assert obs["final_seal"]["state_hash"] == "a" * 64
    assert obs["final_seal"]["sealed_at"] == "2026-08-17T00:00:00Z"
    assert "semantic" not in obs
    assert "provenance" not in obs


def test_build_hext_observation_optional_fields():
    obs = build_hext_observation(
        "obs-1", "hello", "a" * 64, "2026-08-17T00:00:00Z",
        metadata={"k": "v"}, provenance_agents=["agent-1"],
    )
    assert obs["semantic"]["metadata"] == {"k": "v"}
    assert obs["provenance"]["contributors"] == [{"agent": "agent-1"}]


# ---------------------------------------------------------------------------
# MeaningMapper response parsing (Stage 1: single real observation)
# ---------------------------------------------------------------------------


def test_single_observation_produces_measurement_not_trajectory():
    result = run_meaning_trajectory([_observation(0)])
    assert len(result.steps) == 1
    assert result.steps[0].quarantined is False
    assert result.steps[0].measurement is not None
    assert result.steps[0].measurement.dimension == 8  # meaning_mapper.MEANING_SPACE_DIMENSION
    assert result.stabilized is False  # dwell_steps default is 5; one step is not enough


def test_quarantined_observation_is_recorded_not_silently_dropped():
    malformed = {"object": {"id": "bad-1"}}  # missing evidence/final_seal
    result = run_meaning_trajectory([malformed])
    assert len(result.steps) == 1
    assert result.steps[0].quarantined is True
    assert result.steps[0].quarantine_detail is not None
    assert result.steps[0].measurement is None
    assert result.stabilized is False


def test_quarantined_observation_does_not_stop_the_run():
    malformed = {"object": {"id": "bad-1"}}
    observations = [malformed] + [_observation(i) for i in range(1, 6)]
    result = run_meaning_trajectory(observations)
    assert result.steps[0].quarantined is True
    assert any(not s.quarantined for s in result.steps[1:])


# ---------------------------------------------------------------------------
# Trajectory validation — real stabilization, empirically confirmed recipe
# ---------------------------------------------------------------------------


def test_repeated_stable_observation_produces_real_trajectory():
    observations = [_observation(i) for i in range(8)]
    result = run_meaning_trajectory(observations)

    assert result.stabilized is True
    assert isinstance(result, TrajectoryRunResult)
    trajectory = result.trajectory
    assert trajectory is not None
    assert trajectory.dwell_steps == 5
    assert trajectory.is_novel is True  # empty field prior (bootstrap mode) -> no known basin
    assert len(trajectory.centroid) == 8
    assert len(trajectory.covariance) == 8
    # Stops as soon as stabilization is reached — does not consume all 8 inputs.
    assert len(result.steps) < len(observations)


def test_trajectory_run_stops_at_first_stabilization():
    observations = [_observation(i) for i in range(20)]
    result = run_meaning_trajectory(observations)
    assert result.stabilized is True
    assert len(result.steps) == 5  # dwell_steps=5, stabilizes at the 5th ingest (index 4)


def test_insufficient_observations_do_not_stabilize():
    observations = [_observation(i) for i in range(3)]  # fewer than dwell_steps=5
    result = run_meaning_trajectory(observations)
    assert result.stabilized is False
    assert len(result.steps) == 3
    assert all(not s.quarantined for s in result.steps)


def test_empty_observation_list():
    result = run_meaning_trajectory([])
    assert result.steps == ()
    assert result.stabilized is False
