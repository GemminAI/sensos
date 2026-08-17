"""MeaningMapper -> meaning-space-runtime (MSR) -> Trajectory.

Wires two real, already-versioned upstream libraries (installed as local
dependencies, not vendored — see requirements.txt) into one function this
Runtime can call. Neither library is modified: both are treated as opaque
dependencies, consumed only through their public API.

Wire contract, confirmed from the actual code (not assumed from docs):

- `meaning_mapper.map_observation(HEXTObservation) -> MeasurementResult`
  (`meaning_mapper/pipeline.py`). Its output, `MeaningMeasurement.as_dict()`,
  is DOCUMENTED as structurally compatible with MSR's
  `msr.adapters.mapper.measurement_from_payload()` — verified true here:
  every key `measurement_from_payload` looks for (`theta`, `sigma`,
  `observation_id`, `frame_id`, `timestamp_ns`, `provenance`) is present
  in `as_dict()`'s output under those exact names.
- `msr.runtime.MeaningSpaceRuntime.ingest(MeaningMeasurement) -> StepResult`
  drives the fast loop; `StepResult.stabilized` is a real
  `msr.abi.StabilizedTrajectory` once `StabilizationDetector`'s dwell
  criterion is met (default 5 consecutive quiescent steps in the same
  basin) — confirmed empirically this cycle: 5 repeated real measurements
  of the same real HEXT Observation content (with increasing timestamps)
  stabilize at step index 4.

IMPORTANT — what this module does NOT claim: v1.4's Canonical Observation /
EOU concepts are unrelated to this. A `StabilizedTrajectory` is real,
measured geometric data from a real deterministic pipeline; it is not an
EOU-128-v1 ensemble, and no Var[S]/H_comp/Triad computation happens on it
anywhere in this module.

CLE note (Phase 1 finding, not fixed here): `meaning_mapper.cle.grounding.
ground_observation()` and `meaning_mapper.map_observation()` are
INDEPENDENT, parallel consumers of the same raw HEXT Observation — CLE's
grounding output does NOT feed into the measurement pipeline anywhere in
meaning-mapper's actual code (confirmed by reading
`meaning_mapper/cle/grounding.py`'s own docstring: "neither is derived
from the other"). So there is no real "CLE -> MeaningMapper" data
dependency to wire here; this module intentionally does not invent one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import meaning_mapper
from msr.abi import MeaningMeasurement as MSRMeasurement
from msr.abi import StabilizedTrajectory
from msr.adapters.mapper import measurement_from_payload
from msr.runtime import MeaningSpaceRuntime, StepResult


def build_hext_observation(
    observation_id: str,
    text: str,
    state_hash: str,
    sealed_at: str,
    *,
    metadata: dict[str, Any] | None = None,
    provenance_agents: list[str] | None = None,
) -> dict[str, Any]:
    """Construct a real, valid HEXT Observation — the exact wire shape
    `meaning_mapper.validation.observation_validation.validate_observation()`
    checks for (`object.id`, `evidence.body`, `final_seal.state_hash`,
    `final_seal.sealed_at`, optional `semantic.metadata`/
    `provenance.contributors`), confirmed by reading that module directly.
    Not a mock: every field here is exactly what meaning-mapper's own
    validator requires and nothing it doesn't check for.
    """
    observation: dict[str, Any] = {
        "object": {"id": observation_id},
        "evidence": {"body": text},
        "final_seal": {"state_hash": state_hash, "sealed_at": sealed_at},
    }
    if metadata:
        observation["semantic"] = {"metadata": metadata}
    if provenance_agents:
        observation["provenance"] = {
            "contributors": [{"agent": agent} for agent in provenance_agents]
        }
    return observation


@dataclass(frozen=True)
class TrajectoryStepOutcome:
    """What happened for one HEXT Observation fed into the chain."""

    observation_id: str
    quarantined: bool
    quarantine_detail: str | None = None
    measurement: MSRMeasurement | None = None
    step: StepResult | None = None


@dataclass(frozen=True)
class TrajectoryRunResult:
    steps: tuple[TrajectoryStepOutcome, ...] = field(default_factory=tuple)
    trajectory: StabilizedTrajectory | None = None

    @property
    def stabilized(self) -> bool:
        return self.trajectory is not None


def run_meaning_trajectory(observations: list[dict[str, Any]]) -> TrajectoryRunResult:
    """Feed a sequence of real HEXT Observations through
    MeaningMapper -> MSR, in order, on one `MeaningSpaceRuntime` instance.

    Pure and synchronous (no I/O) — matches the actual nature of both
    upstream libraries (neither does network/disk I/O; confirmed in the
    Reality Audit). `frame_id`/`dimension` are taken from the FIRST valid
    measurement, since `MeaningSpaceRuntime` requires both upfront and
    meaning-mapper's own `theta` dimension (8, from
    `meaning_mapper._constants.MEANING_SPACE_DIMENSION`) is a property of
    its pipeline, not something this module decides.

    A quarantined observation (real, honest outcome — not converted to a
    fake measurement) is skipped for `ingest()` but recorded in `steps`.
    Returns as soon as a real `StabilizedTrajectory` is produced, or after
    all observations are consumed with none.
    """
    steps: list[TrajectoryStepOutcome] = []
    runtime: MeaningSpaceRuntime | None = None

    for observation in observations:
        result = meaning_mapper.map_observation(observation)
        observation_id = observation.get("object", {}).get("id", "<unknown>")

        if result.is_quarantined:
            steps.append(
                TrajectoryStepOutcome(
                    observation_id=observation_id,
                    quarantined=True,
                    quarantine_detail=result.quarantine.detail,
                )
            )
            continue

        measurement_payload = result.measurement.as_dict()
        msr_measurement = measurement_from_payload(measurement_payload)

        if runtime is None:
            runtime = MeaningSpaceRuntime(
                frame_id=msr_measurement.frame_id, dimension=msr_measurement.dimension
            )

        step = runtime.ingest(msr_measurement)
        steps.append(
            TrajectoryStepOutcome(
                observation_id=observation_id,
                quarantined=False,
                measurement=msr_measurement,
                step=step,
            )
        )

        if step.did_stabilize:
            return TrajectoryRunResult(steps=tuple(steps), trajectory=step.stabilized)

    return TrajectoryRunResult(steps=tuple(steps), trajectory=None)
