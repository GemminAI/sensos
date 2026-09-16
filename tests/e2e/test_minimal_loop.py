"""Phase 3: one real pass of MeaningMapper -> MSR -> CLE -> hekb-vnext.

Run with the nvs-runtime venv, which already has meaning_mapper/msr
installed and categorical-lift-engine editable-installed this session:

    /Users/tomonam3/GemminAI/sensos/services/nvs-runtime/.venv/bin/python3 \\
        -m pytest tests/e2e/test_minimal_loop.py -v

No new adapter code exists between any two stages except the HEKB write:

- MeaningMapper -> MSR: `runtime.services.meaning_trajectory.run_meaning_trajectory`
  (already implemented and used by this repo's own nvs-runtime service;
  reused verbatim here, not reimplemented).
- MSR -> CLE: no adapter. `msr.abi.StabilizedTrajectory` satisfies
  `cle.abi.inputs.StabilizedTrajectoryLike` structurally (pinned by
  `sensos-core`'s own Phase 2 test,
  `tests/test_trajectory_cle_protocol.py`) and is passed to
  `CLEEngine.lift()` unmodified.
- CLE -> hekb-vnext: the one genuinely new piece this phase adds --
  `dev_hekb_writer.DevHekbWriter`, a dev/test-only signer for the real
  `X-Audit-Signature` governance gate `POST /experience` requires.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

NVS_RUNTIME_ROOT = Path("/Users/tomonam3/GemminAI/sensos/services/nvs-runtime")
if str(NVS_RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(NVS_RUNTIME_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from cle.runtime.engine import CLEEngine  # noqa: E402
from runtime.services.meaning_trajectory import build_hext_observation, run_meaning_trajectory  # noqa: E402

from dev_hekb_writer import DevHekbWriter  # noqa: E402


def _json_safe(obj):
    """Walks a CLE `LiftResult` (nested frozen dataclasses + a `frozenset`
    of morphism triples) into plain JSON-safe types. Test-local glue, not a
    new library abstraction -- `LiftResult` has no `as_dict()` of its own."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _json_safe(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, (frozenset, set)):
        return sorted(_json_safe(v) for v in obj)
    if isinstance(obj, (tuple, list)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    return obj


def _five_repeated_observations() -> list[dict]:
    """5 HEXT Observations of identical content, increasing `sealed_at` --
    the exact recipe `meaning_trajectory.py`'s own docstring documents as
    stabilizing at step index 4 (default 5-step dwell criterion)."""
    return [
        build_hext_observation(
            observation_id=f"phase3-e2e-obs-{i}",
            text="the kernel observed a quiescent basin",
            state_hash=f"state-hash-{i:02d}",
            sealed_at=f"2026-09-17T00:00:{i:02d}Z",
        )
        for i in range(5)
    ]


def test_minimal_meaningmapper_msr_cle_hekb_loop():
    # 1. MeaningMapper -> MSR (reused, not reimplemented)
    trajectory_run = run_meaning_trajectory(_five_repeated_observations())
    assert trajectory_run.stabilized, "expected the 5 repeated observations to stabilize"
    trajectory = trajectory_run.trajectory

    # 2. MSR -> CLE: no adapter, no conversion.
    lift_result = CLEEngine().lift(trajectory)
    assert lift_result.proof.is_valid

    # 3. CLE -> hekb-vnext, via the one new piece this phase adds.
    payload = {
        "schema": "hekb.experience/1",
        "raw_input": {
            "trajectory_id": trajectory.trajectory_id,
            "observation_ids": [step.observation_id for step in trajectory_run.steps],
        },
        "resolved_meaning": _json_safe(lift_result),
        "action": None,
        "title": f"Phase 3 minimal loop: {trajectory.trajectory_id}",
        "tags": ["sensos-phase3-e2e"],
        "ext": {
            "frame_id": trajectory.frame_id,
            "basin_id": trajectory.basin_id,
            "dwell_steps": trajectory.dwell_steps,
            "dwell_seconds": trajectory.dwell_seconds,
            "centroid": list(trajectory.centroid),
        },
    }

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        writer = DevHekbWriter.start(Path(tmp) / "experience")
        expected_object_id = writer.expected_object_id(payload)
        stored = writer.create_experience(payload)

        # 4. Verify the returned object_id is the real SHA-256 content
        # address, computed independently by hekb-vnext's own MemoryObject
        # -- not merely "the call returned 2xx".
        assert stored["object_id"] == expected_object_id
        assert stored["lineage_id"] == expected_object_id  # root of a new lineage
        assert stored["parent_id"] is None
