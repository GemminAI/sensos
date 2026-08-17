"""Meaning Triangulation — measures how stable a meaning structure is across
independent observation paths, using only real MeaningMapper/MSR output
(`runtime.services.meaning_trajectory.run_meaning_trajectory`). No new
"correctness of meaning" score is computed anywhere in this module.

What a "path" is, concretely (not invented — these are the observation
patterns the existing test suite for meaning_trajectory already exercises,
see runtime/tests/test_meaning_trajectory.py):

  - a set of HEXT Observations built from *repeated identical text*
    (`test_repeated_stable_observation_produces_real_trajectory`)
  - the same input *replayed* through a fresh run (determinism check —
    `run_meaning_trajectory` is documented pure/synchronous, no I/O)
  - a set of HEXT Observations built from *paraphrased/reworded text*
    (a genuinely different textual surface for a claimed-same meaning)

Each path is run through the real chain independently (its own fresh
`MeaningSpaceRuntime`, exactly as `run_meaning_trajectory` already does —
no new runtime wiring). What comes out is compared using only fields MSR
itself already computes and already exposes on `StabilizedTrajectory`:
`centroid` (real geometric position), `basin_id` (MSR's own notion of
"known region of meaning space"), `is_novel`, `dwell_steps`,
`dwell_seconds`.

Known, honestly-documented limitation (not papered over): every path run
through `run_meaning_trajectory` today starts a *fresh* `MeaningSpaceRuntime`
with no field prior (see that module's own docstring — bootstrap mode).
So every stabilization currently has `basin_id=None`/`is_novel=True`, and
"same basin_id" is trivially true across any number of paths today — it is
NOT a meaningful cross-path agreement signal until a shared field prior is
wired in (out of scope for this prototype). `same_basin` is still reported
per pair, but flagged `basin_signal_meaningful=False` whenever both sides
are novel, so a caller cannot mistake a trivial match for a real one.

Classification (`TriangulationState`) intentionally does NOT default to a
built-in numeric cutoff on centroid distance — that cutoff would be exactly
the kind of invented "how close counts as the same meaning" magic number
this cycle's instructions prohibit. Real pairwise Euclidean centroid
distances (the same formula `GemminAI/hekb`'s own `query.py` uses for
vector comparison — no new metric invented) are always computed and
reported; the aggregate STABLE/DIVERGENT verdict is only produced when the
caller explicitly supplies `divergence_epsilon`. Without it, `state` is
`NOT_EVALUABLE` with a note explaining why — an honest "we have not decided
what counts as divergent" rather than a silently fabricated threshold.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from runtime.services.meaning_trajectory import TrajectoryRunResult, run_meaning_trajectory


class TriangulationState(StrEnum):
    STABLE = "STABLE"
    DIVERGENT = "DIVERGENT"
    NOT_EVALUABLE = "NOT_EVALUABLE"


@dataclass(frozen=True)
class TriangulationInput:
    """One observation path — provenance identity for that path plus the
    real HEXT Observations to run through it. `method` is a caller-supplied
    label (e.g. "repeated_stable", "replay", "paraphrase") describing how
    this path's observations were produced; this module does not infer or
    validate it — that judgment belongs to the caller, not this measurer."""

    path_id: str
    observations: list[dict[str, Any]]
    method: str


@dataclass(frozen=True)
class TriangulationMeasurement:
    """One path's real, measured outcome. `run_result` is the actual
    `TrajectoryRunResult` from `run_meaning_trajectory` — nothing here is
    derived beyond what that function already returns."""

    path_id: str
    method: str
    observation_ids: tuple[str, ...]
    run_result: TrajectoryRunResult

    @property
    def stabilized(self) -> bool:
        return self.run_result.stabilized

    @property
    def centroid(self) -> tuple[float, ...] | None:
        return self.run_result.trajectory.centroid if self.run_result.trajectory else None

    @property
    def basin_id(self) -> str | None:
        return self.run_result.trajectory.basin_id if self.run_result.trajectory else None

    @property
    def is_novel(self) -> bool | None:
        return self.run_result.trajectory.is_novel if self.run_result.trajectory else None


def euclidean_distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Same formula GemminAI/hekb's own query.py euclidean_distance() uses
    (sqrt of summed squared component differences) — no new metric
    invented, kept consistent with the rest of this ecosystem."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


@dataclass(frozen=True)
class PairwiseComparison:
    """Raw, real measured comparison between two paths' outcomes. Always
    populated when both paths stabilized and share the same dimension;
    `centroid_distance`/`same_basin` are None when a comparison genuinely
    cannot be made (one/both did not stabilize, or dimensions differ —
    real, honest gaps, not coerced to a fake number)."""

    path_a: str
    path_b: str
    both_stabilized: bool
    dimension_match: bool | None
    centroid_distance: float | None
    same_basin: bool | None
    basin_signal_meaningful: bool
    dwell_steps_a: int | None
    dwell_steps_b: int | None


@dataclass(frozen=True)
class TriangulationResult:
    triangulation_id: str
    measurements: tuple[TriangulationMeasurement, ...]
    pairwise: tuple[PairwiseComparison, ...]
    state: TriangulationState
    divergence_epsilon: float | None
    note: str


def run_meaning_triangulation(
    inputs: list[TriangulationInput],
    *,
    triangulation_id: str,
    divergence_epsilon: float | None = None,
) -> TriangulationResult:
    """Runs each `TriangulationInput` through the real, unmodified
    MeaningMapper -> MSR chain independently, then reports how the
    resulting stabilized centroids relate to one another.

    Does not require exactly 3 paths — any number >= 0. Fewer than 2
    successfully stabilized paths means there is nothing to triangulate
    against, which is NOT_EVALUABLE, not a fabricated STABLE/DIVERGENT
    guess.
    """
    measurements: list[TriangulationMeasurement] = []
    for triangulation_input in inputs:
        run_result = run_meaning_trajectory(triangulation_input.observations)
        observation_ids = tuple(
            observation.get("object", {}).get("id", "<unknown>")
            for observation in triangulation_input.observations
        )
        measurements.append(
            TriangulationMeasurement(
                path_id=triangulation_input.path_id,
                method=triangulation_input.method,
                observation_ids=observation_ids,
                run_result=run_result,
            )
        )

    pairwise: list[PairwiseComparison] = []
    for i in range(len(measurements)):
        for j in range(i + 1, len(measurements)):
            a, b = measurements[i], measurements[j]
            both_stabilized = a.stabilized and b.stabilized
            dimension_match: bool | None = None
            centroid_distance: float | None = None
            same_basin: bool | None = None
            basin_signal_meaningful = False

            if both_stabilized:
                dimension_match = len(a.centroid) == len(b.centroid)
                if dimension_match:
                    centroid_distance = euclidean_distance(a.centroid, b.centroid)
                same_basin = a.basin_id == b.basin_id
                # See module docstring: "same basin" is only a meaningful
                # cross-path signal when at least one side is a real,
                # known-basin match, not a trivial both-novel None==None.
                basin_signal_meaningful = not (a.is_novel and b.is_novel)

            pairwise.append(
                PairwiseComparison(
                    path_a=a.path_id,
                    path_b=b.path_id,
                    both_stabilized=both_stabilized,
                    dimension_match=dimension_match,
                    centroid_distance=centroid_distance,
                    same_basin=same_basin,
                    basin_signal_meaningful=basin_signal_meaningful,
                    dwell_steps_a=(a.run_result.trajectory.dwell_steps if a.stabilized else None),
                    dwell_steps_b=(b.run_result.trajectory.dwell_steps if b.stabilized else None),
                )
            )

    stabilized_count = sum(1 for m in measurements if m.stabilized)
    comparable_distances = [p.centroid_distance for p in pairwise if p.centroid_distance is not None]

    if stabilized_count < 2:
        state = TriangulationState.NOT_EVALUABLE
        note = f"only {stabilized_count} of {len(measurements)} path(s) stabilized; nothing to triangulate against"
    elif divergence_epsilon is None:
        state = TriangulationState.NOT_EVALUABLE
        note = (
            f"{stabilized_count} paths stabilized and {len(comparable_distances)} pairwise centroid "
            "distances were measured, but no divergence_epsilon was supplied — this module does not "
            "invent a default distance cutoff for 'the same meaning' (see module docstring)"
        )
    elif not comparable_distances:
        state = TriangulationState.NOT_EVALUABLE
        note = "stabilized paths have mismatched meaning-space dimensions; no centroid distance is comparable"
    elif max(comparable_distances) <= divergence_epsilon:
        state = TriangulationState.STABLE
        note = f"max pairwise centroid distance {max(comparable_distances):.6g} <= divergence_epsilon {divergence_epsilon:.6g}"
    else:
        state = TriangulationState.DIVERGENT
        note = f"max pairwise centroid distance {max(comparable_distances):.6g} > divergence_epsilon {divergence_epsilon:.6g}"

    return TriangulationResult(
        triangulation_id=triangulation_id,
        measurements=tuple(measurements),
        pairwise=tuple(pairwise),
        state=state,
        divergence_epsilon=divergence_epsilon,
        note=note,
    )
