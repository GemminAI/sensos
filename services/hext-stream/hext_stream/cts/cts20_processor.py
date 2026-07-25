"""CTS-20: Processor Extension Conformance Test."""

from __future__ import annotations

import csv
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hext_stream.cts.context import RuntimeSession
from hext_stream.processors import (
    DEFAULT_TOPIC_MAP,
    DiagramProcessor,
    FlowProcessor,
    KanProcessor,
    ObservationProcessor,
    Pipeline,
    ProcessorRegistry,
    TrajectoryProcessor,
    stamp_processor_metadata,
)
from hext_stream.schema.base import HextObject, utcnow


@dataclass
class CTS20Result:
    test_id: str
    name: str
    passed: bool
    details: str = ""
    measurements: dict[str, Any] = field(default_factory=dict)


@dataclass
class CTS20Report:
    backend: str
    results: list[CTS20Result] = field(default_factory=list)
    pipeline_events: list[HextObject] = field(default_factory=list)

    def add(self, r: CTS20Result) -> None:
        self.results.append(r)


class CTS20Runner:
    """CTS-20 processor extension conformance tests."""

    def __init__(self, session: RuntimeSession) -> None:
        self.session = session
        self.run_id = uuid.uuid4().hex[:8]
        self._register_topics()

    def _iso_topic(self, event_type: str) -> str:
        base = DEFAULT_TOPIC_MAP.get(event_type, event_type)
        return f"CTS20{base}-{self.run_id}"

    def _register_topics(self) -> None:
        if not self.session.runtime:
            return
        for event_type in DEFAULT_TOPIC_MAP:
            self.session.runtime.router.register(self._iso_topic(event_type))
        self.session.runtime.router.register(f"CTS20Diagnostic-{self.run_id}")

    def _publish_fn(self, topic: str, obj: HextObject) -> str:
        if self.session.runtime:
            self.session.runtime.router.register(topic)
        return self.session.publish(topic, obj).event_id

    def _make_observation(self) -> HextObject:
        return HextObject(
            id=f"hext:cts20:obs-{self.run_id}",
            timestamp=utcnow(),
            source="cts-20",
            type="observation",
            version="1.0.0",
            payload={"sequence": 1},
            metadata={"session": "cts20"},
        )

    def run_all(self) -> CTS20Report:
        report = CTS20Report(backend=self.session.backend_name)
        tests = [
            self.cts_20_1_registration,
            self.cts_20_2_dispatch,
            self.cts_20_3_pipeline_execution,
            self.cts_20_4_metadata_preservation,
            self.cts_20_5_history_compatibility,
            self.cts_20_6_replay_compatibility,
            self.cts_20_7_determinism,
        ]
        for fn in tests:
            try:
                report.add(fn(report))
            except Exception as exc:
                report.add(CTS20Result(fn.__name__, fn.__name__, False, f"EXCEPTION: {exc}"))
        return report

    def cts_20_1_registration(self, report: CTS20Report) -> CTS20Result:
        registry = ProcessorRegistry()
        obs = ObservationProcessor()
        traj = TrajectoryProcessor()
        pid_obs = registry.register(obs)
        pid_traj = registry.register(traj)
        listed = registry.list()
        got_obs = registry.get(pid_obs)
        unreg_ok = registry.unregister(pid_traj)
        got_after = registry.get(pid_traj)
        passed = (
            len(listed) == 2
            and got_obs is obs
            and unreg_ok
            and got_after is None
            and len(registry.list()) == 1
        )
        return CTS20Result(
            "CTS-20.1", "Processor Registration", passed,
            f"registered=2 after_unregister=1 unreg_ok={unreg_ok}",
            {"registered": len(listed), "remaining": len(registry.list())},
        )

    def cts_20_2_dispatch(self, report: CTS20Report) -> CTS20Result:
        registry = ProcessorRegistry()
        registry.register(ObservationProcessor())
        registry.register(TrajectoryProcessor())
        obs = self._make_observation()
        traj_outputs = registry.dispatch(obs)
        traj_ok = len(traj_outputs) == 1 and traj_outputs[0].type == "trajectory"
        flow_outputs = registry.dispatch(traj_outputs[0])
        flow_ok = len(flow_outputs) == 1 and flow_outputs[0].type == "trajectory.flow"
        passed = traj_ok and flow_ok
        return CTS20Result(
            "CTS-20.2", "Dispatch Correctness", passed,
            f"traj_outputs={len(traj_outputs)} flow_outputs={len(flow_outputs)}",
            {"traj_ok": traj_ok, "flow_ok": flow_ok},
        )

    def cts_20_3_pipeline_execution(self, report: CTS20Report) -> CTS20Result:
        obs = self._make_observation()
        pipeline = Pipeline(
            ObservationProcessor(),
            TrajectoryProcessor(),
            FlowProcessor(),
            DiagramProcessor(),
            KanProcessor(),
            publish_fn=self._publish_fn,
            topic_resolver=lambda et: self._iso_topic(et),
        )
        published = pipeline.execute(self._iso_topic("observation"), obs)
        report.pipeline_events = published
        types_seen = {e.type for e in published}
        expected = {
            "observation", "trajectory", "trajectory.flow",
            "hom", "diagram", "rewrite", "kan_completion",
        }
        passed = expected.issubset(types_seen) and len(published) >= 7
        return CTS20Result(
            "CTS-20.3", "Pipeline Execution", passed,
            f"published={len(published)} types={sorted(types_seen)}",
            {"count": len(published), "types": sorted(types_seen)},
        )

    def cts_20_4_metadata_preservation(self, report: CTS20Report) -> CTS20Result:
        if not report.pipeline_events:
            pipeline = Pipeline(
                ObservationProcessor(),
                TrajectoryProcessor(),
                publish_fn=self._publish_fn,
                topic_resolver=lambda et: self._iso_topic(et),
            )
            report.pipeline_events = pipeline.execute(
                self._iso_topic("observation"), self._make_observation(),
            )

        derived = [e for e in report.pipeline_events if e.type == "trajectory"]
        if not derived:
            return CTS20Result("CTS-20.4", "Metadata Preservation", False, "no derived events")

        original = derived[0]
        proc_meta = original.metadata.get("processor", {})
        history_ok = True
        replay_ok = True
        subscribe_ok = True

        iso = self._iso_topic("trajectory")
        for h in self.session.history(iso, limit=50):
            if h.id == original.id:
                if h.metadata.get("processor", {}).get("type") != proc_meta.get("type"):
                    history_ok = False
        for r in self.session.replay(iso, last_n=50):
            if r.id == original.id:
                if r.metadata.get("processor", {}).get("id") != proc_meta.get("id"):
                    replay_ok = False

        if self.session._mode != "http":
            received: list[HextObject] = []
            test = stamp_processor_metadata(
                HextObject(source="cts-20", type="trajectory", payload={}),
                ObservationProcessor(),
                execution_time_ms=1.0,
            )
            diag = f"CTS20Diagnostic-{self.run_id}"
            if self.session.runtime:
                self.session.runtime.router.register(diag)
            handle = self.session.subscribe(diag, received.append)
            self.session.publish(diag, test)
            time.sleep(0.2)
            self.session.unsubscribe(handle)
            matching = [o for o in received if o.metadata.get("processor")]
            subscribe_ok = len(matching) >= 1

        passed = history_ok and replay_ok and subscribe_ok and bool(proc_meta.get("type"))
        return CTS20Result(
            "CTS-20.4", "Metadata Preservation", passed,
            f"history={history_ok} replay={replay_ok} subscribe={subscribe_ok} proc_type={proc_meta.get('type')}",
            {"history": history_ok, "replay": replay_ok, "subscribe": subscribe_ok},
        )

    def cts_20_5_history_compatibility(self, report: CTS20Report) -> CTS20Result:
        if not report.pipeline_events:
            return CTS20Result("CTS-20.5", "History Compatibility", False, "no pipeline events")

        types_found: set[str] = set()
        for event_type in ("trajectory", "hom", "diagram", "kan_completion"):
            iso = self._iso_topic(event_type)
            for obj in self.session.history(iso, limit=100):
                if obj.id.startswith("hext:cts20:") or obj.metadata.get("processor"):
                    types_found.add(obj.type)

        passed = len(types_found) >= 3
        return CTS20Result(
            "CTS-20.5", "History Compatibility", passed,
            f"types_in_history={sorted(types_found)}",
            {"types": sorted(types_found)},
        )

    def cts_20_6_replay_compatibility(self, report: CTS20Report) -> CTS20Result:
        if not report.pipeline_events:
            return CTS20Result("CTS-20.6", "Replay Compatibility", False, "no pipeline events")

        replay_ok = True
        for event_type in ("trajectory", "trajectory.flow", "hom"):
            iso = self._iso_topic(event_type)
            replayed = self.session.replay(iso, last_n=100)
            hist = self.session.history(iso, limit=100)
            if len(replayed) != len(hist):
                replay_ok = False
            for r, h in zip(replayed, hist):
                if r.id != h.id or r.metadata.get("processor") != h.metadata.get("processor"):
                    replay_ok = False

        passed = replay_ok
        return CTS20Result(
            "CTS-20.6", "Replay Compatibility", passed,
            f"replay_matches_history={replay_ok}",
            {"replay_ok": replay_ok},
        )

    def cts_20_7_determinism(self, report: CTS20Report) -> CTS20Result:
        if not report.pipeline_events:
            return CTS20Result("CTS-20.7", "Determinism", False, "no pipeline events")

        iso = self._iso_topic("trajectory")
        graphs: list[list[dict[str, Any]]] = []
        for _ in range(3):
            replayed = self.session.replay(iso, last_n=50)
            graphs.append([
                {
                    "id": e.id,
                    "type": e.type,
                    "proc": e.metadata.get("processor", {}).get("type"),
                }
                for e in replayed
                if e.metadata.get("processor")
            ])
        identical = graphs[0] == graphs[1] == graphs[2] and len(graphs[0]) > 0
        return CTS20Result(
            "CTS-20.7", "Determinism", identical,
            f"triplicate_identical={identical}",
            {"triplicate_identical": identical},
        )


def run_backend_comparison(
    inprocess_report: CTS20Report,
    redis_report: CTS20Report,
) -> CTS20Result:
    in_types = {e.type for e in inprocess_report.pipeline_events}
    redis_types = {e.type for e in redis_report.pipeline_events}
    isomorphic = in_types == redis_types and len(inprocess_report.pipeline_events) == len(redis_report.pipeline_events)
    return CTS20Result(
        "CTS-20.8", "Backend Compatibility",
        isomorphic,
        f"inprocess_types={sorted(in_types)} redis_types={sorted(redis_types)} match={isomorphic}",
        {"isomorphic": isomorphic},
    )


def export_cts20_artifacts(
    reports: dict[str, CTS20Report],
    comparison: CTS20Result | None,
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    graph_doc: dict[str, Any] = {}
    for backend, rep in reports.items():
        graph_doc[backend] = [
            {
                "id": e.id,
                "type": e.type,
                "processor": e.metadata.get("processor"),
            }
            for e in rep.pipeline_events
        ]
    (out_dir / "processor_pipeline.json").write_text(json.dumps(graph_doc, indent=2), encoding="utf-8")

    rows: list[dict[str, Any]] = []
    for backend, rep in reports.items():
        for r in rep.results:
            rows.append({
                "backend": backend,
                "test_id": r.test_id,
                "passed": r.passed,
                "details": r.details,
            })
    if comparison:
        rows.append({
            "backend": "comparison",
            "test_id": comparison.test_id,
            "passed": comparison.passed,
            "details": comparison.details,
        })
    with (out_dir / "processor_report.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["backend", "test_id", "passed", "details"])
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# CTS-20 Processor Extension Conformance Report\n\n",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n",
        "## Purpose\n\n",
        "Validate HEXT STREAM v1.1 Processor Layer without modifying Core ABI.\n\n",
    ]
    for backend, rep in reports.items():
        passed = sum(1 for r in rep.results if r.passed)
        total = len(rep.results)
        lines.append(f"## Backend: `{backend}`\n\n")
        lines.append(f"**Pass rate:** {passed}/{total}\n\n")
        lines.append("| Test | PASS | Details |\n|------|------|--------|\n")
        for r in rep.results:
            lines.append(f"| {r.test_id} {r.name} | {'PASS' if r.passed else 'FAIL'} | {r.details} |\n")
        lines.append("\n")
    if comparison:
        lines.append(f"## CTS-20.8 Backend Compatibility\n\n**{'PASS' if comparison.passed else 'FAIL'}** — {comparison.details}\n\n")
    all_pass = all(
        r.passed for name in ("inprocess", "redis") if name in reports for r in reports[name].results
    ) and (comparison.passed if comparison else True)
    lines.append(f"## Overall Verdict\n\n**{'PASS' if all_pass else 'FAIL'}**\n")
    (out_dir / "processor_report.md").write_text("".join(lines), encoding="utf-8")
