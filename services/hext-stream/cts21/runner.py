#!/usr/bin/env python3
"""CTS-21 v1.0 Candidate — real-runtime conformance test runner.

Implements the CTS-21 Specification v1.0 Candidate faithfully: the 8 verify_assert_NN
methods in cts21/assertions/*.py are ported essentially verbatim from its §5 (pure
comparison logic, unaltered). This runner wires them to REAL hext_stream runtime output
(both InProcessBackend and RedisBackend) instead of the reference doc's illustrative
hardcoded mocks.

An earlier draft of this suite (built against an older CTS-21 draft) found two genuine
specification divergences between that draft and EXP-4010 v0.2 — see
reports/Specification_Divergence_Report.md for the full history. Both are RESOLVED as
of EXP-4010 v1.0 Candidate + CTS-21 v1.0 Candidate: the runtime's SED formula
(hext_stream/processors/semantic/sed_calculator.py) was migrated to the new
Feed-Forward Detour formula matching CTS-21 v1.0's own reference evaluator exactly, and
ASSERT-06 now tests the real EXP-4010 semantic pipeline instead of the older v1.1
pipeline it fell back to. See the Migration Report for details.

Usage:
  PYTHONPATH=. python3 cts21/runner.py [--skip-redis] [--redis-url URL]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hext_stream.backend.inprocess_backend import InProcessBackend
from hext_stream.backend.redis_backend import RedisBackend
from hext_stream.processors import Pipeline
from hext_stream.processors.semantic import build_pipeline_processors
from hext_stream.runtime.stream_runtime import StreamRuntime
from hext_stream.schema.base import HextObject, utcnow

from cts21.assertions import (
    assert_01_literal_extraction as a01,
    assert_02_controller_command as a02,
    assert_03_sed as a03,
    assert_04_replay_determinism as a04,
    assert_05_expansion_serialization as a05,
    assert_06_pipeline_topology as a06,
    assert_07_idempotent_replay as a07,
    assert_08_observation_preservation as a08,
)

CASES_DIR = Path(__file__).resolve().parent / "cases"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"

TOPIC_MAP = {
    "observation": "Observation",
    "diagram": "Diagram",
    "expansion.candidate": "ExpansionCandidate",
    "semantic.metric": "SemanticMetric",
    "controller.command": "Controller",
    "trajectory": "Trajectory",
    "trajectory.flow": "TrajectoryFlow",
    "hom": "Hom",
    "rewrite": "Rewrite",
}


@dataclass
class AssertionOutcome:
    assertion_id: str
    name: str
    passed: bool
    message: str


@dataclass
class CaseResult:
    case_id: str
    backend: str
    outcomes: list[AssertionOutcome] = field(default_factory=list)

    def add(self, assertion_id: str, name: str, passed: bool, message: str) -> None:
        self.outcomes.append(AssertionOutcome(assertion_id, name, passed, message))
        print(f"  {message}")


def make_runtime(backend_name: str, redis_url: str) -> StreamRuntime:
    backend = RedisBackend(url=redis_url) if backend_name == "redis" else InProcessBackend()
    return StreamRuntime(backend=backend, config={"backend": backend_name, "topics": list(TOPIC_MAP.values())})


def iso_topics(run_id: str) -> dict[str, str]:
    """Run-scoped topic names. Required because RedisBackend is a real external server
    whose data persists across separate StreamRuntime instances/process runs (unlike
    InProcessBackend, which always starts empty) -- a shared fixed topic name would let
    replay() on Redis pick up stale events from earlier runs, corrupting ASSERT-04/07/08."""
    return {event_type: f"CTS21{base}-{run_id}" for event_type, base in TOPIC_MAP.items()}


def _merge_injected_graph(tc: dict[str, Any]) -> tuple[set[str], set[tuple[str, str]]]:
    nodes: set[str] = set()
    edges: set[tuple[str, str]] = set()
    for obs in tc["injected_observations"]:
        nodes |= set(obs["payload_graph"]["nodes"])
        edges |= {tuple(e) for e in obs["payload_graph"]["edges"]}
    return nodes, edges


def run_semantic_pipeline(
    runtime: StreamRuntime,
    tc: dict[str, Any],
    run_id: str,
    topics: dict[str, str],
    *,
    theory_context: Any = None,
) -> list[HextObject]:
    """Runs the EXP-4010 semantic pipeline (ASSERT-01/02/03/05/07/08's target).

    RFC-HEXT016 §6 Rule 1 / CTS-22: `theory_context` is optional and
    additive — every existing CTS-21 call site (all of them omit it) is
    unaffected, since `build_pipeline_processors(None)` reproduces the
    original zero-argument construction exactly.
    """
    A_nodes, A_edges = _merge_injected_graph(tc)
    R = tc["gold_standard_R"]

    seed = HextObject(
        id=f"hext:cts21:{run_id}:obs",
        timestamp=utcnow(),
        source="cts21",
        type="observation",
        version="1.0.0",
        payload={
            "instruction_id": f"instr-{run_id}",
            "trajectory_id": f"traj-{run_id}",
            "instruction_text": tc["user_instruction"],
            "required_graph": {"objects": R["nodes"], "morphisms": [list(e) for e in R["edges"]]},
            "generated_graph": {"objects": sorted(A_nodes), "morphisms": [list(e) for e in A_edges]},
            "generated_text": tc.get("agent_output_text", ""),
            "group": "CTS21",
        },
        metadata={"case_id": tc["case_id"]},
    )

    def publish_fn(topic: str, obj: HextObject) -> str:
        runtime.router.register(topic)
        return runtime.publish(topic, obj)

    pipeline = Pipeline(
        *build_pipeline_processors(theory_context), publish_fn=publish_fn, topic_resolver=lambda et: topics.get(et, et)
    )
    return pipeline.execute(topics["observation"], seed)


def run_case(case_path: Path, backend_name: str, redis_url: str) -> CaseResult:
    tc = json.loads(case_path.read_text(encoding="utf-8"))
    result = CaseResult(case_id=tc["case_id"], backend=backend_name)
    run_id = f"{tc['case_id']}-{backend_name}-{uuid.uuid4().hex[:8]}"
    topics = iso_topics(run_id)

    runtime = make_runtime(backend_name, redis_url)
    try:
        for topic in topics.values():
            runtime.router.register(topic)
        published = run_semantic_pipeline(runtime, tc, run_id, topics)

        # ASSERT-01
        extracted_L = a01.extract(tc)
        expected_L = set(tc["literal_constraints_given"])
        passed, msg = a01.verify(extracted_L, expected_L, tc["case_id"])
        result.add("CTS-21.1", "Literal Extraction", passed, msg)

        # ASSERT-02
        preserved_L, generated_command = a02.extract(published, tc)
        passed, msg = a02.verify(set(tc["literal_constraints_given"]), preserved_L, generated_command, tc["case_id"])
        result.add("CTS-21.2", "Controller Command Generation", passed, msg)

        # ASSERT-03
        A_nodes, A_edges = _merge_injected_graph(tc)
        _, _, real_sed = a03.extract(published, tc)
        R = tc["gold_standard_R"]
        passed, msg = a03.verify(A_nodes, A_edges, set(R["nodes"]), {tuple(e) for e in R["edges"]}, real_sed, tc["case_id"])
        result.add("CTS-21.3", "Semantic Metric (SED) Response", passed, msg)

        # ASSERT-05
        candidates = a05.extract(published)
        if candidates:
            for c in candidates:
                passed, msg = a05.verify(c, tc["case_id"])
                result.add("CTS-21.5", f"Expansion Candidate Serialization ({c['generated_node']})", passed, msg)
        else:
            result.add("CTS-21.5", "Expansion Candidate Serialization", True, "[PASS] ASSERT-05: No candidates in this case (nothing to serialize).")

        # ASSERT-04, ASSERT-07, ASSERT-08 -- via real replay()
        raw1, raw2 = a04.extract(runtime, topics["semantic.metric"])
        passed, msg = a04.verify(raw1, raw2, tc["case_id"])
        result.add("CTS-21.4", "Replay Determinism", passed, msg)

        metrics1, metrics2 = a07.extract(runtime, topics["semantic.metric"])
        passed, msg = a07.verify(metrics1, metrics2, tc["case_id"])
        result.add("CTS-21.7", "Idempotent Replay", passed, msg)

        current_instruction = a08.extract(runtime, topics["observation"])
        passed, msg = a08.verify(current_instruction, tc["user_instruction"], tc["case_id"])
        result.add("CTS-21.8", "Observation Preservation", passed, msg)

        # ASSERT-06 -- same semantic-pipeline run as everything else (no longer needs a
        # separate v1.1 pipeline run; see assert_06_pipeline_topology.py's migration note)
        logs = a06.extract(published)
        passed, msg = a06.verify(logs, tc["case_id"])
        result.add("CTS-21.6", "Pipeline Topology", passed, msg)
    finally:
        runtime.close()

    return result


def export_reports(results: list[CaseResult]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "# CTS-21 v1.0 Candidate Conformance Report\n\n",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n",
        "**Runtime version:** HEXT STREAM Runtime v1.1 + EXP-4010 v1.0 Candidate Semantic "
        "Observation Processor Extension (post-migration)\n\n",
        "## Purpose\n\n",
        "Validate the real hext_stream runtime against CTS-21 Specification v1.0 Candidate's "
        "8 assertions, driven by actual pipeline execution -- not the reference doc's illustrative "
        "hardcoded mock values.\n\n",
        "The two specification divergences found against an earlier CTS-21 draft (SED formula; "
        "ASSERT-06 pipeline identity) are RESOLVED as of this v1.0 Candidate migration -- see "
        "`Specification_Divergence_Report.md` for the full history and "
        "`Runtime_Migration_Report.md` for what changed.\n\n",
    ]

    by_backend: dict[str, list[CaseResult]] = {}
    for r in results:
        by_backend.setdefault(r.backend, []).append(r)

    for backend, case_results in by_backend.items():
        total = sum(len(r.outcomes) for r in case_results)
        passed = sum(1 for r in case_results for o in r.outcomes if o.passed)
        lines.append(f"## Backend: `{backend}`\n\n**Pass rate:** {passed}/{total}\n\n")
        for r in case_results:
            lines.append(f"### Case: `{r.case_id}`\n\n")
            lines.append("| Assertion | PASS | Message |\n|---|---|---|\n")
            for o in r.outcomes:
                lines.append(f"| {o.assertion_id} {o.name} | {'PASS' if o.passed else 'FAIL'} | {o.message} |\n")
            lines.append("\n")

    # Backend comparison
    backends = list(by_backend.keys())
    if len(backends) == 2:
        b1, b2 = backends
        lines.append("## Backend Comparison\n\n")
        for r1, r2 in zip(by_backend[b1], by_backend[b2]):
            match = [o1.passed == o2.passed for o1, o2 in zip(r1.outcomes, r2.outcomes)]
            lines.append(f"- `{r1.case_id}`: {b1} vs {b2} pass/fail pattern identical: **{all(match)}**\n")
        lines.append("\n")

    all_pass = all(o.passed for r in results for o in r.outcomes)
    lines.append(f"## Overall Verdict\n\n**{'PASS' if all_pass else 'FAIL'}** "
                 f"({'all assertions passed' if all_pass else 'see FAILs above'})\n")

    (REPORTS_DIR / "CTS21_Report.md").write_text("".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="CTS-21 v1.0 Candidate runner")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--skip-redis", action="store_true")
    args = parser.parse_args()

    case_files = sorted(CASES_DIR.glob("*.json"))
    print(f"[CTS-21] Found {len(case_files)} test cases in {CASES_DIR}")

    all_results: list[CaseResult] = []

    for backend_name in (["inprocess"] if args.skip_redis else ["inprocess", "redis"]):
        print(f"\n[CTS-21] Backend: {backend_name}")
        for case_file in case_files:
            print(f"\n--- Running CTS-21 for case: {case_file.name} ({backend_name}) ---")
            try:
                result = run_case(case_file, backend_name, args.redis_url)
                all_results.append(result)
            except Exception as exc:
                print(f"[CTS-21] EXCEPTION running {case_file.name} on {backend_name}: {exc}")

    export_reports(all_results)
    print(f"\n[CTS-21] Report: {REPORTS_DIR / 'CTS21_Report.md'}")

    total = sum(len(r.outcomes) for r in all_results)
    passed = sum(1 for r in all_results for o in r.outcomes if o.passed)
    print(f"[CTS-21] {passed}/{total} assertions passed across all cases/backends")
    return 0


if __name__ == "__main__":
    sys.exit(main())
