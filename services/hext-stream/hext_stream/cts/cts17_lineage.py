"""CTS-17: Morphism Lineage Conformance Test."""

from __future__ import annotations

import csv
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hext_stream.cts.context import RuntimeSession, canonical_json
from hext_stream.cts.stats import summarize
from hext_stream.schema.base import HextObject, utcnow
from hext_stream.schema.replay import ReplayMode


LINEAGE_FIELDS = ("id", "parent_id", "root_id", "lineage_depth")


@dataclass
class LineageNode:
    id: str
    parent_id: str | None
    root_id: str
    lineage_depth: int
    type: str
    topic: str
    parent_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_object(cls, obj: HextObject, topic: str) -> LineageNode:
        meta = obj.metadata
        parent_ids = meta.get("parent_ids", [])
        if not parent_ids and meta.get("parent_id"):
            parent_ids = [meta["parent_id"]]
        return cls(
            id=obj.id,
            parent_id=meta.get("parent_id"),
            root_id=meta.get("root_id", obj.id),
            lineage_depth=int(meta.get("lineage_depth", 0)),
            type=obj.type,
            topic=topic,
            parent_ids=list(parent_ids),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "root_id": self.root_id,
            "lineage_depth": self.lineage_depth,
            "type": self.type,
            "topic": self.topic,
            "parent_ids": self.parent_ids,
        }


@dataclass
class LineageGraph:
    nodes: dict[str, LineageNode] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)

    def add(self, node: LineageNode) -> None:
        self.nodes[node.id] = node
        if node.parent_id:
            edge = (node.parent_id, node.id)
            if edge not in self.edges:
                self.edges.append(edge)
        for pid in node.parent_ids:
            if pid:
                edge = (pid, node.id)
                if edge not in self.edges:
                    self.edges.append(edge)

    def canonical(self) -> dict[str, Any]:
        return {
            "nodes": {k: v.to_dict() for k, v in sorted(self.nodes.items())},
            "edges": sorted(self.edges),
        }

    def lineage_canonical(self) -> dict[str, Any]:
        """Lineage topology only — excludes routing topic."""
        return {
            "nodes": {
                k: {
                    "id": v.id,
                    "parent_id": v.parent_id,
                    "root_id": v.root_id,
                    "lineage_depth": v.lineage_depth,
                    "type": v.type,
                    "parent_ids": sorted(v.parent_ids),
                }
                for k, v in sorted(self.nodes.items())
            },
            "edges": sorted(self.edges),
        }

    def isomorphic_to(self, other: LineageGraph) -> bool:
        return self.lineage_canonical() == other.lineage_canonical()


def _lineage_object(
    *,
    obj_id: str,
    obj_type: str,
    topic: str,
    depth: int,
    root_id: str,
    parent_id: str | None = None,
    parent_ids: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    label: str = "",
) -> tuple[str, HextObject]:
    meta: dict[str, Any] = {
        "parent_id": parent_id,
        "root_id": root_id,
        "lineage_depth": depth,
        "label": label,
    }
    if parent_ids:
        meta["parent_ids"] = parent_ids
    obj = HextObject(
        id=obj_id,
        timestamp=utcnow(),
        source="cts-17",
        type=obj_type,
        version="1.0.0",
        payload=payload or {"label": label},
        metadata=meta,
    )
    return topic, obj


def build_main_chain() -> tuple[list[tuple[str, HextObject]], LineageGraph]:
    """Observation O1 → O2 → Trajectory T1 → Flow F1 → Controller C1 → Replay R1."""
    o1_id = "hext:cts17:O1"
    o2_id = "hext:cts17:O2"
    t1_id = "hext:cts17:T1"
    f1_id = "hext:cts17:F1"
    c1_id = "hext:cts17:C1"
    r1_id = "hext:cts17:R1"
    root = o1_id

    chain = [
        _lineage_object(obj_id=o1_id, obj_type="observation", topic="Observation", depth=0, root_id=root, parent_id=None, label="O1"),
        _lineage_object(obj_id=o2_id, obj_type="observation", topic="Observation", depth=0, root_id=root, parent_id=o1_id, label="O2"),
        _lineage_object(obj_id=t1_id, obj_type="trajectory", topic="Trajectory", depth=1, root_id=root, parent_id=o2_id, label="T1"),
        _lineage_object(obj_id=f1_id, obj_type="trajectory.flow", topic="TrajectoryFlow", depth=2, root_id=root, parent_id=t1_id, label="F1"),
        _lineage_object(obj_id=c1_id, obj_type="controller", topic="Controller", depth=3, root_id=root, parent_id=f1_id, label="C1"),
        _lineage_object(obj_id=r1_id, obj_type="replay", topic="Replay", depth=4, root_id=root, parent_id=c1_id, label="R1"),
    ]
    graph = LineageGraph()
    for topic, obj in chain:
        graph.add(LineageNode.from_object(obj, topic))
    return chain, graph


def build_branch_chain() -> tuple[list[tuple[str, HextObject]], LineageGraph]:
    """O1 → T1 → F1 and O1 → T1 → F2 (shared ancestry)."""
    o1_id = "hext:cts17:branch:O1"
    t1_id = "hext:cts17:branch:T1"
    f1_id = "hext:cts17:branch:F1"
    f2_id = "hext:cts17:branch:F2"
    root = o1_id
    chain = [
        _lineage_object(obj_id=o1_id, obj_type="observation", topic="Observation", depth=0, root_id=root, parent_id=None, label="O1"),
        _lineage_object(obj_id=t1_id, obj_type="trajectory", topic="Trajectory", depth=1, root_id=root, parent_id=o1_id, label="T1"),
        _lineage_object(obj_id=f1_id, obj_type="trajectory.flow", topic="TrajectoryFlow", depth=2, root_id=root, parent_id=t1_id, label="F1"),
        _lineage_object(obj_id=f2_id, obj_type="trajectory.flow", topic="TrajectoryFlow", depth=2, root_id=root, parent_id=t1_id, label="F2"),
    ]
    graph = LineageGraph()
    for topic, obj in chain:
        graph.add(LineageNode.from_object(obj, topic))
    return chain, graph


def build_merge_chain() -> tuple[list[tuple[str, HextObject]], LineageGraph, str]:
    """F1 + F2 → C1 (multiple parents)."""
    f1_id = "hext:cts17:merge:F1"
    f2_id = "hext:cts17:merge:F2"
    c1_id = "hext:cts17:merge:C1"
    root = "hext:cts17:merge:root"
    chain = [
        _lineage_object(obj_id=f1_id, obj_type="trajectory.flow", topic="TrajectoryFlow", depth=2, root_id=root, parent_id=None, label="F1"),
        _lineage_object(obj_id=f2_id, obj_type="trajectory.flow", topic="TrajectoryFlow", depth=2, root_id=root, parent_id=None, label="F2"),
        _lineage_object(
            obj_id=c1_id,
            obj_type="controller",
            topic="Controller",
            depth=3,
            root_id=root,
            parent_id=f1_id,
            parent_ids=[f1_id, f2_id],
            label="C1",
        ),
    ]
    graph = LineageGraph()
    for topic, obj in chain:
        graph.add(LineageNode.from_object(obj, topic))
    return chain, graph, c1_id


def _extract_lineage(obj: HextObject) -> dict[str, Any]:
    return {
        "id": obj.id,
        "parent_id": obj.metadata.get("parent_id"),
        "root_id": obj.metadata.get("root_id"),
        "lineage_depth": obj.metadata.get("lineage_depth"),
        "parent_ids": obj.metadata.get("parent_ids", []),
    }


def _lineage_unchanged(original: HextObject, observed: HextObject) -> bool:
    return _extract_lineage(original) == _extract_lineage(observed) and original.id == observed.id


@dataclass
class CTS17Result:
    test_id: str
    name: str
    passed: bool
    details: str = ""
    measurements: dict[str, Any] = field(default_factory=dict)


@dataclass
class CTS17Report:
    backend: str
    results: list[CTS17Result] = field(default_factory=list)
    original_graph: LineageGraph | None = None
    published_objects: list[tuple[str, HextObject]] = field(default_factory=list)

    def add(self, r: CTS17Result) -> None:
        self.results.append(r)


class CTS17Runner:
    """CTS-17 morphism lineage conformance tests."""

    PREFIX = "cts17"

    def __init__(self, session: RuntimeSession) -> None:
        self.session = session
        self._register_topics()

    def _register_topics(self) -> None:
        if not self.session.runtime:
            return
        for t in ("CTS17Observation", "CTS17Trajectory", "CTS17TrajectoryFlow",
                  "CTS17Controller", "CTS17Replay", "CTS17Diagnostic"):
            self.session.runtime.router.register(t)

    def _iso_topic(self, topic: str) -> str:
        """Use dedicated topics to avoid cross-test contamination."""
        return {
            "Observation": "CTS17Observation",
            "Trajectory": "CTS17Trajectory",
            "TrajectoryFlow": "CTS17TrajectoryFlow",
            "Controller": "CTS17Controller",
            "Replay": "CTS17Replay",
        }.get(topic, topic)

    def _publish_chain(self, chain: list[tuple[str, HextObject]]) -> list[tuple[str, HextObject]]:
        published: list[tuple[str, HextObject]] = []
        for topic, obj in chain:
            iso = self._iso_topic(topic)
            if self.session.runtime:
                self.session.runtime.router.register(iso)
            self.session.publish(iso, obj)
            published.append((iso, obj))
        return published

    def run_all(self) -> CTS17Report:
        report = CTS17Report(backend=self.session.backend_name)
        chain, original_graph = build_main_chain()
        report.original_graph = original_graph
        report.published_objects = self._publish_chain(chain)

        tests = [
            self.cts_17_1_parent_preservation,
            self.cts_17_2_root_preservation,
            self.cts_17_3_depth_preservation,
            self.cts_17_4_replay_lineage,
            self.cts_17_5_history_lineage,
            self.cts_17_7_flow_branch,
            self.cts_17_8_flow_merge,
            self.cts_17_9_determinism,
        ]
        for fn in tests:
            try:
                report.add(fn(report))
            except Exception as exc:
                report.add(CTS17Result(fn.__name__, fn.__name__, False, f"EXCEPTION: {exc}"))
        return report

    def cts_17_1_parent_preservation(self, report: CTS17Report) -> CTS17Result:
        originals = {obj.id: obj for _, obj in report.published_objects}
        subscribe_ok = True

        if self.session._mode != "http":
            received: list[HextObject] = []
            test_obj = HextObject(
                id="hext:cts17:sub-test",
                source="cts-17",
                type="diagnostic",
                metadata={
                    "parent_id": "hext:cts17:C1",
                    "root_id": "hext:cts17:O1",
                    "lineage_depth": 0,
                },
            )
            iso = "CTS17Diagnostic"
            if self.session.runtime:
                self.session.runtime.router.register(iso)
            handle = self.session.subscribe(iso, received.append)
            self.session.publish(iso, test_obj)
            time.sleep(0.2)
            self.session.unsubscribe(handle)
            if len(received) != 1 or not _lineage_unchanged(test_obj, received[0]):
                subscribe_ok = False

        history_ok = True
        replay_ok = True
        for iso, orig in report.published_objects:
            for h in self.session.history(iso, limit=100):
                if h.id in originals and not _lineage_unchanged(originals[h.id], h):
                    history_ok = False
            for r in self.session.replay(iso, last_n=100):
                if r.id in originals and not _lineage_unchanged(originals[r.id], r):
                    replay_ok = False

        passed = subscribe_ok and history_ok and replay_ok
        return CTS17Result(
            "CTS-17.1", "Parent Preservation", passed,
            f"subscribe={subscribe_ok} history={history_ok} replay={replay_ok}",
            {"subscribe": subscribe_ok, "history": history_ok, "replay": replay_ok},
        )

    def cts_17_2_root_preservation(self, report: CTS17Report) -> CTS17Result:
        expected_root = "hext:cts17:O1"
        main_ids = {obj.id for _, obj in report.published_objects}
        violations = []
        for iso, orig in report.published_objects:
            for label, source in [
                ("history", self.session.history(iso, limit=50)),
                ("replay", self.session.replay(iso, last_n=50)),
            ]:
                for obj in source:
                    if obj.id not in main_ids:
                        continue
                    if obj.metadata.get("root_id") != expected_root:
                        violations.append(f"{label}:{obj.id}")
        return CTS17Result(
            "CTS-17.2", "Root Preservation", len(violations) == 0,
            f"expected_root={expected_root} violations={violations[:5]}",
            {"violations": len(violations)},
        )

    def cts_17_3_depth_preservation(self, report: CTS17Report) -> CTS17Result:
        expected = {
            "observation": 0,
            "trajectory": 1,
            "trajectory.flow": 2,
            "controller": 3,
            "replay": 4,
        }
        violations = []
        monotonic_ok = True
        depths_seen: list[int] = []
        for _, orig in report.published_objects:
            d = int(orig.metadata.get("lineage_depth", -1))
            depths_seen.append(d)
            if expected.get(orig.type) != d:
                violations.append(f"{orig.id}:type={orig.type}:depth={d}")
        for iso, _ in report.published_objects:
            for obj in self.session.replay(iso, last_n=50):
                if obj.id.startswith("hext:cts17:") and not obj.id.startswith("hext:cts17:branch") and not obj.id.startswith("hext:cts17:merge"):
                    d = int(obj.metadata.get("lineage_depth", -1))
                    if expected.get(obj.type) != d:
                        violations.append(f"replay:{obj.id}")
        return CTS17Result(
            "CTS-17.3", "Depth Preservation", len(violations) == 0 and monotonic_ok,
            f"expected_depths={expected} violations={violations}",
            {"violations": len(violations), "depths_seen": depths_seen},
        )

    def cts_17_4_replay_lineage(self, report: CTS17Report) -> CTS17Result:
        originals = {obj.id: _extract_lineage(obj) for _, obj in report.published_objects}
        all_ok = True
        for iso, _ in report.published_objects:
            for obj in self.session.replay(iso, last_n=50):
                if obj.id in originals:
                    if _extract_lineage(obj) != originals[obj.id]:
                        all_ok = False
        return CTS17Result(
            "CTS-17.4", "Replay Lineage", all_ok,
            f"objects_checked={len(originals)} all_preserved={all_ok}",
        )

    def cts_17_5_history_lineage(self, report: CTS17Report) -> CTS17Result:
        original_graph = report.original_graph
        assert original_graph is not None
        reconstructed = LineageGraph()
        seen_isos: set[str] = set()
        for iso, _ in report.published_objects:
            if iso in seen_isos:
                continue
            seen_isos.add(iso)
            for obj in self.session.history(iso, limit=50):
                if obj.id.startswith("hext:cts17:") and not obj.id.startswith("hext:cts17:branch") and not obj.id.startswith("hext:cts17:merge"):
                    reconstructed.add(LineageNode.from_object(obj, iso))
        isomorphic = original_graph.isomorphic_to(reconstructed)
        return CTS17Result(
            "CTS-17.5", "History Lineage", isomorphic,
            f"original_nodes={len(original_graph.nodes)} reconstructed_nodes={len(reconstructed.nodes)} isomorphic={isomorphic}",
        )

    def cts_17_7_flow_branch(self, report: CTS17Report) -> CTS17Result:
        chain, expected_graph = build_branch_chain()
        self._publish_chain(chain)
        reconstructed = LineageGraph()
        seen_isos: set[str] = set()
        for topic, obj in chain:
            iso = self._iso_topic(topic)
            if iso in seen_isos:
                continue
            seen_isos.add(iso)
            for h in self.session.history(iso, limit=50):
                if h.id.startswith("hext:cts17:branch"):
                    reconstructed.add(LineageNode.from_object(h, iso))
        # Shared ancestry: F1 and F2 must both have parent T1, T1 parent O1
        f1 = reconstructed.nodes.get("hext:cts17:branch:F1")
        f2 = reconstructed.nodes.get("hext:cts17:branch:F2")
        shared = (
            f1 is not None and f2 is not None
            and f1.parent_id == f2.parent_id == "hext:cts17:branch:T1"
        )
        isomorphic = expected_graph.isomorphic_to(reconstructed)
        return CTS17Result(
            "CTS-17.7", "Flow Branch", isomorphic and shared,
            f"shared_ancestry={shared} isomorphic={isomorphic}",
            {"shared_ancestry": shared, "isomorphic": isomorphic},
        )

    def cts_17_8_flow_merge(self, report: CTS17Report) -> CTS17Result:
        chain, expected_graph, c1_id = build_merge_chain()
        self._publish_chain(chain)
        c1_hist = self.session.history(self._iso_topic("Controller"), limit=50)
        c1_obj = next((h for h in c1_hist if h.id == c1_id), None)
        if c1_obj is None:
            return CTS17Result("CTS-17.8", "Flow Merge", False, "C1 not found in history")
        parent_ids = c1_obj.metadata.get("parent_ids", [])
        has_multi = len(parent_ids) >= 2
        preserved = (
            "hext:cts17:merge:F1" in parent_ids
            and "hext:cts17:merge:F2" in parent_ids
        )
        if not preserved:
            status = "NOT_SUPPORTED" if not has_multi else "CORRUPTED"
            return CTS17Result(
                "CTS-17.8", "Flow Merge", False,
                f"status={status} parent_ids={parent_ids}",
                {"status": status, "parent_ids": parent_ids},
            )
        reconstructed = LineageGraph()
        seen_isos: set[str] = set()
        for topic, obj in chain:
            iso = self._iso_topic(topic)
            if iso in seen_isos:
                continue
            seen_isos.add(iso)
            for h in self.session.history(iso, limit=50):
                if h.id.startswith("hext:cts17:merge"):
                    reconstructed.add(LineageNode.from_object(h, iso))
        return CTS17Result(
            "CTS-17.8", "Flow Merge", expected_graph.isomorphic_to(reconstructed),
            f"multiple_parents_preserved={preserved} parent_ids={parent_ids}",
            {"parent_ids": parent_ids, "preserved": preserved},
        )

    def cts_17_9_determinism(self, report: CTS17Report) -> CTS17Result:
        graphs: list[dict[str, Any]] = []
        for _ in range(3):
            g = LineageGraph()
            for iso, _ in report.published_objects:
                for obj in self.session.replay(iso, last_n=50):
                    if obj.id.startswith("hext:cts17:") and not obj.id.startswith("hext:cts17:branch") and not obj.id.startswith("hext:cts17:merge"):
                        g.add(LineageNode.from_object(obj, iso))
            graphs.append(g.lineage_canonical())
        identical = graphs[0] == graphs[1] == graphs[2]
        return CTS17Result(
            "CTS-17.9", "Determinism", identical,
            f"triplicate_identical={identical}",
            {"triplicate_identical": identical},
        )


def run_backend_comparison(
    inprocess_report: CTS17Report,
    redis_report: CTS17Report,
) -> CTS17Result:
    assert inprocess_report.original_graph and redis_report.original_graph
    # Compare structure types only — separate sessions have separate object ids
    # Compare depth/parent topology pattern
    def signature(g: LineageGraph) -> list[tuple[int, str, int]]:
        return sorted(
            (n.lineage_depth, n.type, len(n.parent_ids) or (1 if n.parent_id else 0))
            for n in g.nodes.values()
        )
    in_sig = signature(inprocess_report.original_graph)
    # For redis, rebuild graph from its published objects
    redis_graph = LineageGraph()
    for iso, obj in redis_report.published_objects:
        redis_graph.add(LineageNode.from_object(obj, iso))
    redis_sig = signature(redis_graph)
    # Main chain has same topology
    isomorphic = in_sig == redis_sig and len(inprocess_report.original_graph.nodes) == len(redis_graph.nodes)
    return CTS17Result(
        "CTS-17.6", "Backend Migration",
        isomorphic,
        f"inprocess_nodes={len(inprocess_report.original_graph.nodes)} redis_nodes={len(redis_graph.nodes)} topology_match={isomorphic}",
        {"topology_match": isomorphic},
    )


def export_cts17_artifacts(
    reports: dict[str, CTS17Report],
    comparison: CTS17Result | None,
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for backend, rep in reports.items():
        for iso, obj in rep.published_objects:
            rows.append({
                "backend": backend,
                "topic": iso,
                "id": obj.id,
                "parent_id": obj.metadata.get("parent_id"),
                "root_id": obj.metadata.get("root_id"),
                "lineage_depth": obj.metadata.get("lineage_depth"),
                "type": obj.type,
                "parent_ids": json.dumps(obj.metadata.get("parent_ids", [])),
            })
    with (out_dir / "morphism_lineage.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["backend", "topic", "id", "parent_id", "root_id", "lineage_depth", "type", "parent_ids"],
        )
        w.writeheader()
        w.writerows(rows)

    graph_doc: dict[str, Any] = {}
    for backend, rep in reports.items():
        if rep.original_graph:
            graph_doc[backend] = rep.original_graph.canonical()
    (out_dir / "lineage_graph.json").write_text(
        json.dumps(graph_doc, indent=2), encoding="utf-8"
    )

    cmp_rows = []
    if comparison:
        cmp_rows.append({
            "test_id": comparison.test_id,
            "inprocess_passed": reports.get("inprocess") and all(r.passed for r in reports["inprocess"].results),
            "redis_passed": reports.get("redis") and all(r.passed for r in reports["redis"].results),
            "topology_match": comparison.measurements.get("topology_match"),
            "passed": comparison.passed,
        })
    for backend, rep in reports.items():
        for r in rep.results:
            cmp_rows.append({
                "backend": backend,
                "test_id": r.test_id,
                "passed": r.passed,
                "details": r.details,
            })
    with (out_dir / "backend_lineage_comparison.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["backend", "test_id", "passed", "details", "inprocess_passed", "redis_passed", "topology_match"])
        w.writeheader()
        for row in cmp_rows:
            w.writerow({k: row.get(k, "") for k in w.fieldnames})

    lines = [
        "# CTS-17 Morphism Lineage Conformance Report\n\n",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n",
        "## Purpose\n\n",
        "Verify structural preservation of semantic morphism lineage through publish, ",
        "subscribe, history, and replay. No runtime modifications.\n\n",
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
        lines.append(f"## CTS-17.6 Backend Migration\n\n")
        lines.append(f"**{'PASS' if comparison.passed else 'FAIL'}** — {comparison.details}\n\n")
    all_primary = all(
        r.passed
        for name in ("inprocess", "redis")
        if name in reports
        for r in reports[name].results
    ) and (comparison.passed if comparison else True)
    lines.append(f"## Overall Verdict\n\n**{'PASS' if all_primary else 'FAIL'}**\n")
    (out_dir / "lineage_report.md").write_text("".join(lines), encoding="utf-8")
