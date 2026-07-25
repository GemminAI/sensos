#!/usr/bin/env python3
"""CTS-23: Deterministic Theory Replay & Theory Diff — RFC-HEXT016 §7/§8/§9 Rule 1.

End-to-end: publishes a seed `observation` to a REAL `StreamRuntime` (both
backends), sources a `ReplayHandle` from real published history via
`ReplayOrchestrator` (RFC-HEXT015 §3) exactly as `TrajectoryManager` does,
then exercises Theory Replay (§7), Theory Diff (§8), and the DevTools
`ReplayController.play` entry point (§9 Rule 7) — the same three surfaces
RC1 Milestones 5-6 built, run against real (not hand-constructed)
`ReplayHandle`s.

Reuses CTS-21's case fixtures (`CASES_DIR`) and `make_runtime`/`iso_topics`
helpers directly — no new fixtures, no new runtime wiring.

Usage:
  PYTHONPATH=. python3 cts21/cts23_replay_diff.py [--skip-redis] [--redis-url URL]
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

from hext_stream.kernel.context import KernelContext  # noqa: F401  (import first: sidesteps a pre-existing devtools<->telemetry<->kernel circular-import ordering issue, unrelated to CTS-23 itself)
from cts21.runner import CASES_DIR, iso_topics, make_runtime
from hext_stream.devtools.replay_controller import ReplayController
from hext_stream.schema.base import HextObject, utcnow
from hext_stream.theory.context import TheoryContext
from hext_stream.theory.manager import TheoryManager
from hext_stream.trajectory.replay import ReplayOrchestrator
from hext_stream.trajectory.diff import TheoryDiff

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


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
        print(f"  [{'PASS' if passed else 'FAIL'}] {assertion_id} {name}: {message}")


def _merge_injected_graph(tc: dict[str, Any]) -> tuple[set[str], set[tuple[str, str]]]:
    nodes: set[str] = set()
    edges: set[tuple[str, str]] = set()
    for obs in tc["injected_observations"]:
        nodes |= set(obs["payload_graph"]["nodes"])
        edges |= {tuple(e) for e in obs["payload_graph"]["edges"]}
    return nodes, edges


def _build_seed(tc: dict[str, Any], run_id: str) -> HextObject:
    A_nodes, A_edges = _merge_injected_graph(tc)
    R = tc["gold_standard_R"]
    return HextObject(
        id=f"hext:cts23:{run_id}:obs",
        timestamp=utcnow(),
        source="cts23",
        type="observation",
        version="1.0.0",
        payload={
            "instruction_id": f"instr-{run_id}",
            "trajectory_id": f"traj-{run_id}",
            "instruction_text": tc["user_instruction"],
            "required_graph": {"objects": R["nodes"], "morphisms": [list(e) for e in R["edges"]]},
            "generated_graph": {"objects": sorted(A_nodes), "morphisms": [list(e) for e in A_edges]},
            "generated_text": tc.get("agent_output_text", ""),
            "group": "CTS23",
        },
        metadata={"case_id": tc["case_id"]},
    )


def _metric_payloads(events) -> list[dict[str, Any]]:
    return [e.payload for e in events]


def run_case(case_path: Path, backend_name: str, redis_url: str) -> CaseResult:
    tc = json.loads(case_path.read_text(encoding="utf-8"))
    result = CaseResult(case_id=tc["case_id"], backend=backend_name)
    run_id = f"{tc['case_id']}-cts23-{backend_name}-{uuid.uuid4().hex[:8]}"
    topics = iso_topics(run_id)

    runtime = make_runtime(backend_name, redis_url)
    try:
        for topic in topics.values():
            runtime.router.register(topic)

        seed = _build_seed(tc, run_id)
        seed_payload_snapshot = dict(seed.payload)
        runtime.publish(topics["observation"], seed)

        orchestrator = ReplayOrchestrator(
            history_fn=runtime.history,
            replay_from_timestamp_fn=runtime.replay_engine.replay_from_timestamp,
            replay_last_n_fn=runtime.replay_engine.replay_last_n,
        )
        handle = orchestrator.last_n(topics["observation"], 10)

        # ASSERT-01: Replay Determinism (default theory) -- two independent
        # `run()` calls over the same real-history-sourced handle produce
        # bit-for-bit identical TheoryResults.
        r1 = handle.run()
        r2 = handle.run()
        det_ok = (
            _metric_payloads(r1.theory_result.metrics) == _metric_payloads(r2.theory_result.metrics)
            and _metric_payloads(r1.theory_result.controller_outputs)
            == _metric_payloads(r2.theory_result.controller_outputs)
        )
        result.add(
            "ASSERT-01", "Replay Determinism", det_ok,
            f"metrics/controller identical across two run() calls: {det_ok}",
        )

        # ASSERT-02: None / explicit-default / TheoryContext.default() parity,
        # through the Replay layer specifically (RFC-HEXT016 §5.4 Rule 1),
        # not just raw pipeline construction (that's CTS-22's job).
        r_none = handle.run(theory_context=None)
        r_default = handle.run(theory_context=TheoryContext.default())
        parity_ok = _metric_payloads(r_none.theory_result.metrics) == _metric_payloads(
            r_default.theory_result.metrics
        )
        result.add(
            "ASSERT-02", "None/Default Parity via Replay", parity_ok,
            f"theory_context=None matches TheoryContext.default() through run(): {parity_ok}",
        )

        # Baseline gain determines whether our alternate theory's raised
        # allow_threshold is *guaranteed* to move the controller action —
        # only meaningful when the baseline action wasn't already forced by
        # LCF's hard-lock branch (gain_to_action checks LCF before either
        # threshold).
        baseline_metrics = r_none.theory_result.metrics[-1].payload.get("metrics", {}) if r_none.theory_result.metrics else {}
        baseline_lcf = baseline_metrics.get("LCF", 0.0)
        baseline_gain = baseline_metrics.get("Gain", 0.0)
        expect_action_change = baseline_lcf >= 1.0

        theory_id = f"cts23-alt-{run_id}"
        tm = TheoryManager()
        tm.loader.load(
            {
                "theory_id": theory_id,
                "version": "1.0",
                "processor_overrides": {
                    "controller": {"allow_threshold": baseline_gain + 0.5, "warn_threshold": 0.0}
                },
            }
        )
        alt_context = tm.context_for(theory_id)
        r_alt = handle.run(theory_context=alt_context)

        # ASSERT-03: TheoryDiff correctness against a theory chosen to
        # deterministically move (or, under hard-lock, deliberately NOT
        # move) the controller action.
        diff = TheoryDiff.compare(r_none, r_alt)
        action_check_ok = diff.controller_delta.action_changed == expect_action_change
        theory_id_ok = diff.summary.theory_id_a is None and diff.summary.theory_id_b == theory_id
        result.add(
            "ASSERT-03", "TheoryDiff Correctness", action_check_ok and theory_id_ok,
            f"expect_action_change={expect_action_change} actual={diff.controller_delta.action_changed} "
            f"(A='{diff.controller_delta.action_a}' B='{diff.controller_delta.action_b}') "
            f"theory_ids=({diff.summary.theory_id_a!r},{diff.summary.theory_id_b!r})",
        )

        # ASSERT-04: TheoryDiff Determinism -- recomputing both the replay
        # and the diff from scratch reproduces identical delta objects.
        r_alt2 = handle.run(theory_context=alt_context)
        diff2 = TheoryDiff.compare(r_none, r_alt2)
        diff_det_ok = (
            diff.metric_deltas == diff2.metric_deltas
            and diff.controller_delta == diff2.controller_delta
            and diff.event_delta == diff2.event_delta
            and diff.summary == diff2.summary
        )
        result.add(
            "ASSERT-04", "TheoryDiff Determinism", diff_det_ok,
            f"metric_deltas/controller_delta/event_delta/summary identical across two compare() calls: {diff_det_ok}",
        )

        # ASSERT-05: Observation Invariance -- the original seed object (and
        # its in-runtime published copy) is untouched by any of the five
        # run() calls above.
        refetched = runtime.history(topics["observation"], limit=10)
        invariance_ok = seed.payload == seed_payload_snapshot and all(
            o.payload == seed_payload_snapshot for o in refetched if o.id == seed.id
        )
        result.add(
            "ASSERT-05", "Observation Invariance", invariance_ok,
            f"seed payload unchanged across 5 run() calls and matches published history: {invariance_ok}",
        )

        # ASSERT-06: ReplayController end-to-end -- the DevTools entry point
        # (RFC-HEXT016 §7 amendment note) produces the same TheoryResult as
        # a direct ReplayHandle.run() call over the identical source data.
        controller = ReplayController(lambda: runtime.history(topics["observation"], limit=10))
        controller.load()
        controller_result = controller.play(theory_context=alt_context)
        controller_ok = (
            controller.is_playing
            and controller.last_replay_result is controller_result
            and _metric_payloads(controller_result.theory_result.metrics)
            == _metric_payloads(r_alt.theory_result.metrics)
            and _metric_payloads(controller_result.theory_result.controller_outputs)
            == _metric_payloads(r_alt.theory_result.controller_outputs)
        )
        result.add(
            "ASSERT-06", "ReplayController End-to-End", controller_ok,
            f"play() result matches direct ReplayHandle.run() over the same source: {controller_ok}",
        )

        # ASSERT-07: Summary Internal Consistency -- every Summary field is
        # independently re-derivable from metric_deltas/controller_delta/event_delta.
        expected_changed = {d.metric_name for d in diff.metric_deltas if d.value_a != d.value_b}
        summary_ok = (
            set(diff.summary.changed_metric_names) == expected_changed
            and diff.summary.action_changed == diff.controller_delta.action_changed
            and diff.summary.event_count_delta == diff.event_delta.count_delta
        )
        result.add(
            "ASSERT-07", "Summary Internal Consistency", summary_ok,
            f"Summary fields match independently-derived values: {summary_ok}",
        )
    finally:
        runtime.close()

    return result


def export_report(results: list[CaseResult]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CTS-23: Deterministic Theory Replay & Theory Diff Report\n\n",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n",
        "## Purpose\n\n",
        "End-to-end validation of RFC-HEXT016 §7 (Theory Replay), §8 (Theory Diff), "
        "and the §9 Rule 7 DevTools entry point (`ReplayController.play`), against real "
        "published history on both backends -- RC1's final milestone.\n\n",
        "| Case | Backend | Assertion | PASS | Detail |\n|---|---|---|---|---|\n",
    ]
    for r in results:
        for o in r.outcomes:
            lines.append(
                f"| {r.case_id} | {r.backend} | {o.assertion_id} {o.name} | "
                f"{'PASS' if o.passed else 'FAIL'} | {o.message} |\n"
            )
    all_pass = all(o.passed for r in results for o in r.outcomes)
    total = sum(len(r.outcomes) for r in results)
    passed = sum(1 for r in results for o in r.outcomes if o.passed)
    lines.append(f"\n## Overall Verdict\n\n**{'PASS' if all_pass else 'FAIL'}** ({passed}/{total} assertions)\n")
    (REPORTS_DIR / "CTS23_Report.md").write_text("".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="CTS-23 Deterministic Theory Replay & Diff runner")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--skip-redis", action="store_true")
    args = parser.parse_args()

    case_files = sorted(CASES_DIR.glob("*.json"))
    print(f"[CTS-23] Found {len(case_files)} test cases in {CASES_DIR}")

    results: list[CaseResult] = []
    for backend_name in (["inprocess"] if args.skip_redis else ["inprocess", "redis"]):
        print(f"\n[CTS-23] Backend: {backend_name}")
        for case_file in case_files:
            print(f" Case: {case_file.stem}")
            try:
                results.append(run_case(case_file, backend_name, args.redis_url))
            except Exception as exc:
                print(f"[CTS-23] EXCEPTION running {case_file.name} on {backend_name}: {exc}")
                failure = CaseResult(case_id=case_file.stem, backend=backend_name)
                failure.add("ASSERT-00", "Exception", False, str(exc))
                results.append(failure)

    export_report(results)
    print(f"\n[CTS-23] Report: {REPORTS_DIR / 'CTS23_Report.md'}")

    total = sum(len(r.outcomes) for r in results)
    passed = sum(1 for r in results for o in r.outcomes if o.passed)
    print(f"[CTS-23] {passed}/{total} assertions passed across all cases/backends")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
