"""CTS-21: Semantic Observation Conformance Test (EXP-4010)."""

from __future__ import annotations

import csv
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hext_stream.cts.context import RuntimeSession
from hext_stream.processors import Pipeline, ProcessorRegistry
from hext_stream.processors.semantic import build_pipeline_processors
from hext_stream.schema.base import HextObject, utcnow

SEMANTIC_TOPIC_MAP: dict[str, str] = {
    "observation": "Observation",
    "diagram": "Diagram",
    "expansion.candidate": "ExpansionCandidate",
    "semantic.metric": "SemanticMetric",
    "controller.command": "Controller",
}


@dataclass
class CTS21Result:
    test_id: str
    name: str
    passed: bool
    details: str = ""
    measurements: dict[str, Any] = field(default_factory=dict)


@dataclass
class CTS21Report:
    backend: str
    results: list[CTS21Result] = field(default_factory=list)
    pipeline_events: list[HextObject] = field(default_factory=list)

    def add(self, r: CTS21Result) -> None:
        self.results.append(r)


class CTS21Runner:
    """CTS-21 semantic observation conformance tests."""

    def __init__(self, session: RuntimeSession) -> None:
        self.session = session
        self.run_id = uuid.uuid4().hex[:8]
        self._register_topics()

    def _iso_topic(self, event_type: str) -> str:
        base = SEMANTIC_TOPIC_MAP.get(event_type, event_type)
        return f"CTS21{base}-{self.run_id}"

    def _register_topics(self) -> None:
        if not self.session.runtime:
            return
        for event_type in SEMANTIC_TOPIC_MAP:
            self.session.runtime.router.register(self._iso_topic(event_type))

    def _publish_fn(self, topic: str, obj: HextObject) -> str:
        if self.session.runtime:
            self.session.runtime.router.register(topic)
        return self.session.publish(topic, obj).event_id

    def _make_seed_observation(self, *, violate_literal: bool = True) -> HextObject:
        generated_text = (
            "saved to /path/to/Draft using a RepositoryFactory pattern"
            if violate_literal
            else "saved to /path/to/Archive using a RepositoryFactory pattern"
        )
        return HextObject(
            id=f"hext:cts21:obs-{self.run_id}",
            timestamp=utcnow(),
            source="cts-21",
            type="observation",
            version="1.0.0",
            payload={
                "instruction_id": f"instr-{self.run_id}",
                "trajectory_id": f"traj-{self.run_id}",
                "instruction_text": "save the JSON to /path/to/Archive only",
                "required_graph": {
                    "objects": ["JSON", "Storage"],
                    "morphisms": [["JSON", "Storage"]],
                },
                "generated_graph": {
                    "objects": ["JSON", "Repository", "Service", "Factory", "Storage"],
                    "morphisms": [
                        ["JSON", "Repository"],
                        ["Repository", "Service"],
                        ["Service", "Factory"],
                        ["Factory", "Storage"],
                    ],
                },
                "generated_text": generated_text,
                "group": "D",
            },
            metadata={"session": "cts21"},
        )

    def _build_pipeline(self) -> Pipeline:
        return Pipeline(
            *build_pipeline_processors(),
            publish_fn=self._publish_fn,
            topic_resolver=lambda et: self._iso_topic(et),
        )

    def run_all(self) -> CTS21Report:
        report = CTS21Report(backend=self.session.backend_name)
        tests = [
            self.cts_21_1_registration,
            self.cts_21_2_pipeline_execution,
            self.cts_21_3_expansion_candidate_preservation,
            self.cts_21_4_semantic_metric_preservation,
            self.cts_21_5_controller_command,
            self.cts_21_6_history_compatibility,
            self.cts_21_7_replay_compatibility,
            self.cts_21_8_determinism,
        ]
        for fn in tests:
            try:
                report.add(fn(report))
            except Exception as exc:
                report.add(CTS21Result(fn.__name__, fn.__name__, False, f"EXCEPTION: {exc}"))
        return report

    def cts_21_1_registration(self, report: CTS21Report) -> CTS21Result:
        registry = ProcessorRegistry()
        ids = [registry.register(p) for p in build_pipeline_processors()]
        listed = registry.list()
        unreg_ok = registry.unregister(ids[0])
        passed = len(listed) == 10 and unreg_ok and len(registry.list()) == 9
        return CTS21Result(
            "CTS-21.1", "Processor Registration", passed,
            f"registered=10 after_unregister=9 unreg_ok={unreg_ok}",
            {"registered": len(listed)},
        )

    def cts_21_2_pipeline_execution(self, report: CTS21Report) -> CTS21Result:
        seed = self._make_seed_observation(violate_literal=True)
        published = self._build_pipeline().execute(self._iso_topic("observation"), seed)
        report.pipeline_events = published
        types_seen = {e.type for e in published}
        expected = {"observation", "diagram", "expansion.candidate", "semantic.metric", "controller.command"}
        passed = expected.issubset(types_seen) and len(published) >= 12
        return CTS21Result(
            "CTS-21.2", "Pipeline Execution", passed,
            f"published={len(published)} types={sorted(types_seen)}",
            {"count": len(published), "types": sorted(types_seen)},
        )

    def cts_21_3_expansion_candidate_preservation(self, report: CTS21Report) -> CTS21Result:
        if not report.pipeline_events:
            return CTS21Result("CTS-21.3", "Expansion Candidate Preservation", False, "no pipeline events")

        candidates = [e for e in report.pipeline_events if e.type == "expansion.candidate"]
        required_keys = {"instruction_id", "trajectory_id", "candidate_type", "generated_node", "processor"}
        fields_ok = all(required_keys.issubset(c.payload.keys()) for c in candidates)
        trajectory_ok = all(c.payload.get("trajectory_id") for c in candidates)

        iso = self._iso_topic("expansion.candidate")
        hist_ids = {h.id for h in self.session.history(iso, limit=50)}
        history_ok = all(c.id in hist_ids for c in candidates)

        passed = len(candidates) >= 1 and fields_ok and trajectory_ok and history_ok
        return CTS21Result(
            "CTS-21.3", "Expansion Candidate Preservation", passed,
            f"candidates={len(candidates)} fields_ok={fields_ok} trajectory_ok={trajectory_ok} history_ok={history_ok}",
            {"count": len(candidates)},
        )

    def cts_21_4_semantic_metric_preservation(self, report: CTS21Report) -> CTS21Result:
        if not report.pipeline_events:
            return CTS21Result("CTS-21.4", "Semantic Metric Preservation", False, "no pipeline events")

        metrics_events = [e for e in report.pipeline_events if e.type == "semantic.metric"]
        # Consolidated design: exactly one pre-Gain vector and one post-Gain vector —
        # NOT one object per metric (SED/OI/IF/LCF are merged into a single vector).
        vector_count_ok = len(metrics_events) == 2
        final = metrics_events[-1] if metrics_events else None
        expected_keys = {"SED", "OI", "IF", "LCF", "Gain"}
        vector_complete = bool(final) and expected_keys.issubset(final.payload.get("metrics", {}).keys())

        iso = self._iso_topic("semantic.metric")
        hist_ids = {h.id for h in self.session.history(iso, limit=50)}
        history_ok = all(m.id in hist_ids for m in metrics_events)

        passed = vector_count_ok and vector_complete and history_ok
        return CTS21Result(
            "CTS-21.4", "Semantic Metric Preservation", passed,
            f"metric_objects={len(metrics_events)} vector_complete={vector_complete} history_ok={history_ok}",
            {"final_metrics": final.payload.get("metrics") if final else {}},
        )

    def cts_21_5_controller_command(self, report: CTS21Report) -> CTS21Result:
        if not report.pipeline_events:
            return CTS21Result("CTS-21.5", "Controller Command (literal violation -> HARD_LOCK)", False, "no pipeline events")

        commands = [e for e in report.pipeline_events if e.type == "controller.command"]
        passed = len(commands) == 1 and commands[0].payload.get("action") == "hard_lock"
        return CTS21Result(
            "CTS-21.5", "Controller Command (literal violation -> HARD_LOCK)", passed,
            f"commands={len(commands)} action={commands[0].payload.get('action') if commands else None}",
            {"commands": len(commands)},
        )

    def cts_21_6_history_compatibility(self, report: CTS21Report) -> CTS21Result:
        if not report.pipeline_events:
            return CTS21Result("CTS-21.6", "History Compatibility", False, "no pipeline events")

        types_found: set[str] = set()
        for event_type in ("diagram", "expansion.candidate", "semantic.metric", "controller.command"):
            iso = self._iso_topic(event_type)
            for obj in self.session.history(iso, limit=100):
                if obj.id.startswith("hext:cts21:") or obj.metadata.get("trajectory_id") or obj.metadata.get("stage") or obj.metadata.get("action"):
                    types_found.add(obj.type)

        passed = len(types_found) >= 3
        return CTS21Result(
            "CTS-21.6", "History Compatibility", passed,
            f"types_in_history={sorted(types_found)}",
            {"types": sorted(types_found)},
        )

    def cts_21_7_replay_compatibility(self, report: CTS21Report) -> CTS21Result:
        if not report.pipeline_events:
            return CTS21Result("CTS-21.7", "Replay Compatibility", False, "no pipeline events")

        replay_ok = True
        for event_type in ("diagram", "semantic.metric", "controller.command"):
            iso = self._iso_topic(event_type)
            replayed = self.session.replay(iso, last_n=100)
            hist = self.session.history(iso, limit=100)
            if len(replayed) != len(hist):
                replay_ok = False
            for r, h in zip(replayed, hist):
                if r.id != h.id or r.payload != h.payload:
                    replay_ok = False

        return CTS21Result(
            "CTS-21.7", "Replay Compatibility", replay_ok,
            f"replay_matches_history={replay_ok}",
            {"replay_ok": replay_ok},
        )

    def cts_21_8_determinism(self, report: CTS21Report) -> CTS21Result:
        if not report.pipeline_events:
            return CTS21Result("CTS-21.8", "Determinism", False, "no pipeline events")

        iso = self._iso_topic("semantic.metric")
        vectors: list[list[dict[str, Any]]] = []
        for _ in range(3):
            replayed = self.session.replay(iso, last_n=50)
            vectors.append([{"id": e.id, "metrics": e.payload.get("metrics")} for e in replayed])
        identical = vectors[0] == vectors[1] == vectors[2] and len(vectors[0]) > 0
        return CTS21Result(
            "CTS-21.8", "Determinism", identical,
            f"triplicate_identical={identical}",
            {"triplicate_identical": identical},
        )


def run_backend_comparison(
    inprocess_report: CTS21Report,
    redis_report: CTS21Report,
) -> CTS21Result:
    in_types = {e.type for e in inprocess_report.pipeline_events}
    redis_types = {e.type for e in redis_report.pipeline_events}
    isomorphic = in_types == redis_types and len(inprocess_report.pipeline_events) == len(redis_report.pipeline_events)
    return CTS21Result(
        "CTS-21.9", "Backend Compatibility",
        isomorphic,
        f"inprocess_types={sorted(in_types)} redis_types={sorted(redis_types)} match={isomorphic}",
        {"isomorphic": isomorphic},
    )


def export_cts21_artifacts(
    reports: dict[str, CTS21Report],
    comparison: CTS21Result | None,
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    graph_doc: dict[str, Any] = {}
    for backend, rep in reports.items():
        graph_doc[backend] = [
            {"id": e.id, "type": e.type, "metadata": e.metadata}
            for e in rep.pipeline_events
        ]
    (out_dir / "semantic_graph.json").write_text(json.dumps(graph_doc, indent=2), encoding="utf-8")

    metric_rows: list[dict[str, Any]] = []
    for backend, rep in reports.items():
        for e in rep.pipeline_events:
            if e.type != "semantic.metric":
                continue
            row = {"backend": backend, "id": e.id, "trajectory_id": e.payload.get("trajectory_id")}
            row.update(e.payload.get("metrics", {}))
            metric_rows.append(row)
    fieldnames = ["backend", "id", "trajectory_id", "SED", "OI", "IF", "LCF", "Gain"]
    with (out_dir / "semantic_metrics.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(metric_rows)

    with (out_dir / "backend_comparison.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["test_id", "passed", "details"])
        w.writeheader()
        if comparison:
            w.writerow({"test_id": comparison.test_id, "passed": comparison.passed, "details": comparison.details})

    lines = [
        "# CTS-21 Semantic Observation Conformance Report\n\n",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n",
        "## Purpose\n\n",
        "Validate EXP-4010's Semantic Observation Processor Layer (passive extension over "
        "HEXT STREAM v1.1) without modifying Core ABI or the existing Processor Layer.\n\n",
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
        lines.append(f"## CTS-21.9 Backend Compatibility\n\n**{'PASS' if comparison.passed else 'FAIL'}** — {comparison.details}\n\n")
    all_pass = all(
        r.passed for name in ("inprocess", "redis") if name in reports for r in reports[name].results
    ) and (comparison.passed if comparison else True)
    lines.append(f"## Overall Verdict\n\n**{'PASS' if all_pass else 'FAIL'}**\n")
    (out_dir / "semantic_report.md").write_text("".join(lines), encoding="utf-8")
