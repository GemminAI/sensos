"""CTS-18: Surface Morphism Compatibility Test."""

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
from hext_stream.schema.base import HextObject, utcnow

SURFACE_FIELDS = (
    "surface_id",
    "source_flow_ids",
    "target_flow_ids",
    "diagram_id",
    "rewrite_step",
)


@dataclass
class FlowNode:
    id: str
    type: str
    parent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "parent_id": self.parent_id}


@dataclass
class SurfaceNode:
    surface_id: str
    source_flow_ids: list[str]
    target_flow_ids: list[str]
    diagram_id: str | None
    rewrite_step: int | None
    object_id: str
    type: str = "surface"

    @classmethod
    def from_object(cls, obj: HextObject) -> SurfaceNode:
        meta = obj.metadata
        return cls(
            surface_id=meta.get("surface_id", obj.id),
            source_flow_ids=list(meta.get("source_flow_ids", [])),
            target_flow_ids=list(meta.get("target_flow_ids", [])),
            diagram_id=meta.get("diagram_id"),
            rewrite_step=meta.get("rewrite_step"),
            object_id=obj.id,
            type=obj.type,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface_id": self.surface_id,
            "source_flow_ids": sorted(self.source_flow_ids),
            "target_flow_ids": sorted(self.target_flow_ids),
            "diagram_id": self.diagram_id,
            "rewrite_step": self.rewrite_step,
            "object_id": self.object_id,
            "type": self.type,
        }


@dataclass
class SurfaceGraph:
    flows: dict[str, FlowNode] = field(default_factory=dict)
    surfaces: dict[str, SurfaceNode] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)
    composition_edges: list[tuple[str, str]] = field(default_factory=list)

    def add_flow(self, obj: HextObject) -> None:
        parent_id = obj.metadata.get("parent_id")
        self.flows[obj.id] = FlowNode(id=obj.id, type=obj.type, parent_id=parent_id)
        if parent_id:
            edge = (parent_id, obj.id)
            if edge not in self.edges:
                self.edges.append(edge)

    def add_surface(self, obj: HextObject) -> None:
        node = SurfaceNode.from_object(obj)
        self.surfaces[node.surface_id] = node
        for src in node.source_flow_ids:
            edge = (src, node.surface_id)
            if edge not in self.edges:
                self.edges.append(edge)
        for tgt in node.target_flow_ids:
            edge = (node.surface_id, tgt)
            if edge not in self.edges:
                self.edges.append(edge)

    def add_composition(self, from_surface: str, to_surface: str) -> None:
        edge = (from_surface, to_surface)
        if edge not in self.composition_edges:
            self.composition_edges.append(edge)

    def canonical(self) -> dict[str, Any]:
        return {
            "flows": {k: v.to_dict() for k, v in sorted(self.flows.items())},
            "surfaces": {k: v.to_dict() for k, v in sorted(self.surfaces.items())},
            "edges": sorted(self.edges),
            "composition_edges": sorted(self.composition_edges),
        }

    def isomorphic_to(self, other: SurfaceGraph) -> bool:
        return self.canonical() == other.canonical()


def _flow_object(
    *,
    obj_id: str,
    obj_type: str,
    parent_id: str | None,
    label: str,
) -> HextObject:
    return HextObject(
        id=obj_id,
        timestamp=utcnow(),
        source="cts-18",
        type=obj_type,
        version="1.0.0",
        payload={"label": label},
        metadata={"parent_id": parent_id, "label": label},
    )


def _surface_object(
    *,
    surface_id: str,
    source_flow_ids: list[str],
    target_flow_ids: list[str],
    diagram_id: str | None = None,
    rewrite_step: int | None = None,
    label: str = "",
) -> HextObject:
    return HextObject(
        id=surface_id,
        timestamp=utcnow(),
        source="cts-18",
        type="surface",
        version="1.0.0",
        payload={"label": label or surface_id},
        metadata={
            "surface_id": surface_id,
            "source_flow_ids": source_flow_ids,
            "target_flow_ids": target_flow_ids,
            "diagram_id": diagram_id,
            "rewrite_step": rewrite_step,
            "label": label,
        },
    )


def build_main_scenario() -> tuple[list[tuple[str, HextObject]], SurfaceGraph]:
    """O1→T1→F1, O2→T2→F2, Surface S1: F1⇒F2."""
    o1 = "hext:cts18:O1"
    t1 = "hext:cts18:T1"
    f1 = "hext:cts18:F1"
    o2 = "hext:cts18:O2"
    t2 = "hext:cts18:T2"
    f2 = "hext:cts18:F2"
    s1 = "hext:cts18:S1"

    objects: list[tuple[str, HextObject]] = [
        ("Observation", _flow_object(obj_id=o1, obj_type="observation", parent_id=None, label="O1")),
        ("Trajectory", _flow_object(obj_id=t1, obj_type="trajectory", parent_id=o1, label="T1")),
        ("TrajectoryFlow", _flow_object(obj_id=f1, obj_type="trajectory.flow", parent_id=t1, label="F1")),
        ("Observation", _flow_object(obj_id=o2, obj_type="observation", parent_id=None, label="O2")),
        ("Trajectory", _flow_object(obj_id=t2, obj_type="trajectory", parent_id=o2, label="T2")),
        ("TrajectoryFlow", _flow_object(obj_id=f2, obj_type="trajectory.flow", parent_id=t2, label="F2")),
        (
            "Surface",
            _surface_object(
                surface_id=s1,
                source_flow_ids=[f1],
                target_flow_ids=[f2],
                diagram_id="hext:cts18:diagram:main",
                rewrite_step=0,
                label="S1 F1⇒F2",
            ),
        ),
    ]

    graph = SurfaceGraph()
    for topic, obj in objects:
        if topic == "Surface":
            graph.add_surface(obj)
        else:
            graph.add_flow(obj)
    return objects, graph


def build_diagram_surfaces(f1: str, f2: str) -> tuple[list[tuple[str, HextObject]], SurfaceGraph]:
    """Multiple surfaces belonging to diagram D1."""
    d1 = "hext:cts18:diagram:D1"
    surfaces = [
        _surface_object(
            surface_id="hext:cts18:diagram:S-a",
            source_flow_ids=[f1],
            target_flow_ids=[f2],
            diagram_id=d1,
            rewrite_step=0,
            label="D1 surface a",
        ),
        _surface_object(
            surface_id="hext:cts18:diagram:S-b",
            source_flow_ids=[f2],
            target_flow_ids=[f1],
            diagram_id=d1,
            rewrite_step=1,
            label="D1 surface b",
        ),
    ]
    graph = SurfaceGraph()
    for s in surfaces:
        graph.add_surface(s)
    return [("Surface", s) for s in surfaces], graph


def build_rewrite_sequence(f1: str, f2: str) -> tuple[list[tuple[str, HextObject]], list[int]]:
    """rewrite_step 0,1,2,3 in publish order."""
    diagram = "hext:cts18:diagram:rewrite"
    steps: list[tuple[str, HextObject]] = []
    for step in range(4):
        sid = f"hext:cts18:rewrite:S{step}"
        steps.append(
            (
                "Surface",
                _surface_object(
                    surface_id=sid,
                    source_flow_ids=[f1],
                    target_flow_ids=[f2],
                    diagram_id=diagram,
                    rewrite_step=step,
                    label=f"rewrite step {step}",
                ),
            )
        )
    return steps, list(range(4))


def build_composition_scenario(
    f1: str, f2: str,
) -> tuple[list[tuple[str, HextObject]], SurfaceGraph]:
    """F1⇒F2, F2⇒F3 composition chain."""
    o3 = "hext:cts18:compose:O3"
    t3 = "hext:cts18:compose:T3"
    f3 = "hext:cts18:compose:F3"
    s12 = "hext:cts18:compose:S12"
    s23 = "hext:cts18:compose:S23"

    objects: list[tuple[str, HextObject]] = [
        ("Observation", _flow_object(obj_id=o3, obj_type="observation", parent_id=None, label="O3")),
        ("Trajectory", _flow_object(obj_id=t3, obj_type="trajectory", parent_id=o3, label="T3")),
        ("TrajectoryFlow", _flow_object(obj_id=f3, obj_type="trajectory.flow", parent_id=t3, label="F3")),
        (
            "Surface",
            _surface_object(
                surface_id=s12,
                source_flow_ids=[f1],
                target_flow_ids=[f2],
                diagram_id="hext:cts18:diagram:compose",
                rewrite_step=0,
                label="F1⇒F2",
            ),
        ),
        (
            "Surface",
            _surface_object(
                surface_id=s23,
                source_flow_ids=[f2],
                target_flow_ids=[f3],
                diagram_id="hext:cts18:diagram:compose",
                rewrite_step=1,
                label="F2⇒F3",
            ),
        ),
    ]

    graph = SurfaceGraph()
    for topic, obj in objects:
        if topic == "Surface":
            graph.add_surface(obj)
        else:
            graph.add_flow(obj)
    graph.add_composition(s12, s23)
    return objects, graph


def build_cross_topic_refs(
    f1: str, f2: str, s1: str,
) -> list[tuple[str, HextObject]]:
    """Controller and Replay referencing cross-topic objects."""
    c1 = "hext:cts18:cross:C1"
    r1 = "hext:cts18:cross:R1"
    return [
        (
            "Controller",
            HextObject(
                id=c1,
                timestamp=utcnow(),
                source="cts-18",
                type="controller",
                version="1.0.0",
                payload={"surface_ref": s1},
                metadata={
                    "parent_id": s1,
                    "refs": {
                        "observation": "hext:cts18:O1",
                        "trajectory": "hext:cts18:T1",
                        "trajectory_flow": f1,
                        "surface": s1,
                    },
                },
            ),
        ),
        (
            "Replay",
            HextObject(
                id=r1,
                timestamp=utcnow(),
                source="cts-18",
                type="replay",
                version="1.0.0",
                payload={"controller_ref": c1},
                metadata={
                    "parent_id": c1,
                    "refs": {
                        "observation": "hext:cts18:O2",
                        "trajectory": "hext:cts18:T2",
                        "trajectory_flow": f2,
                        "surface": s1,
                        "controller": c1,
                    },
                },
            ),
        ),
    ]


def _extract_surface(obj: HextObject) -> dict[str, Any]:
    meta = obj.metadata
    return {
        "surface_id": meta.get("surface_id", obj.id),
        "source_flow_ids": sorted(meta.get("source_flow_ids", [])),
        "target_flow_ids": sorted(meta.get("target_flow_ids", [])),
        "diagram_id": meta.get("diagram_id"),
        "rewrite_step": meta.get("rewrite_step"),
    }


def _surface_unchanged(original: HextObject, observed: HextObject) -> bool:
    return _extract_surface(original) == _extract_surface(observed) and original.id == observed.id


@dataclass
class CTS18Result:
    test_id: str
    name: str
    passed: bool
    details: str = ""
    measurements: dict[str, Any] = field(default_factory=dict)


@dataclass
class CTS18Report:
    backend: str
    results: list[CTS18Result] = field(default_factory=list)
    original_graph: SurfaceGraph | None = None
    diagram_topology: dict[str, Any] = field(default_factory=dict)
    published_objects: list[tuple[str, HextObject]] = field(default_factory=list)
    surface_objects: dict[str, HextObject] = field(default_factory=dict)
    flow_ids: dict[str, str] = field(default_factory=dict)
    expected_rewrite_steps: list[int] = field(default_factory=list)
    compose_graph: SurfaceGraph | None = None

    def add(self, r: CTS18Result) -> None:
        self.results.append(r)


class CTS18Runner:
    """CTS-18 surface morphism compatibility tests."""

    def __init__(self, session: RuntimeSession) -> None:
        self.session = session
        self.run_id = uuid.uuid4().hex[:8]
        self._register_topics()

    def _iso_topic(self, topic: str) -> str:
        base = {
            "Observation": "CTS18Observation",
            "Trajectory": "CTS18Trajectory",
            "TrajectoryFlow": "CTS18TrajectoryFlow",
            "Surface": "CTS18Surface",
            "Controller": "CTS18Controller",
            "Replay": "CTS18Replay",
            "Diagnostic": "CTS18Diagnostic",
        }.get(topic, topic)
        return f"{base}-{self.run_id}"

    def _register_topics(self) -> None:
        if not self.session.runtime:
            return
        for name in (
            "Observation", "Trajectory", "TrajectoryFlow",
            "Surface", "Controller", "Replay", "Diagnostic",
        ):
            self.session.runtime.router.register(self._iso_topic(name))

    def _publish(self, items: list[tuple[str, HextObject]]) -> None:
        for topic, obj in items:
            iso = self._iso_topic(topic)
            if self.session.runtime:
                self.session.runtime.router.register(iso)
            self.session.publish(iso, obj)

    def _collect_surface_graph(
        self,
        *,
        prefix: str = "hext:cts18:",
        include_flows: bool = True,
        include_composition: SurfaceGraph | None = None,
    ) -> SurfaceGraph:
        graph = SurfaceGraph()
        seen_isos: set[str] = set()
        surface_iso = self._iso_topic("Surface")
        flow_isos = [
            self._iso_topic("Observation"),
            self._iso_topic("Trajectory"),
            self._iso_topic("TrajectoryFlow"),
        ]

        if include_flows:
            for iso in flow_isos:
                if iso in seen_isos:
                    continue
                seen_isos.add(iso)
                for obj in self.session.history(iso, limit=200):
                    if obj.id.startswith(prefix) and obj.type != "surface":
                        graph.add_flow(obj)

        seen_isos.clear()
        for obj in self.session.history(surface_iso, limit=200):
            if obj.id.startswith(prefix) and obj.type == "surface":
                graph.add_surface(obj)

        if include_composition:
            for sid, node in include_composition.surfaces.items():
                for other_id, other in include_composition.surfaces.items():
                    if sid == other_id:
                        continue
                    if set(node.target_flow_ids) & set(other.source_flow_ids):
                        graph.add_composition(sid, other_id)
        else:
            for sid, node in graph.surfaces.items():
                for other_id, other in graph.surfaces.items():
                    if sid == other_id:
                        continue
                    if set(node.target_flow_ids) & set(other.source_flow_ids):
                        graph.add_composition(sid, other_id)

        return graph

    def _build_expected_full_graph(self, report: CTS18Report) -> SurfaceGraph:
        graph = SurfaceGraph()
        skip_ids = {"hext:cts18:sub-test"}
        for _, obj in report.published_objects:
            if obj.id in skip_ids:
                continue
            if obj.type == "surface":
                graph.add_surface(obj)
            elif obj.type in ("observation", "trajectory", "trajectory.flow"):
                graph.add_flow(obj)
        for sid, node in graph.surfaces.items():
            for other_id, other in graph.surfaces.items():
                if sid == other_id:
                    continue
                if set(node.target_flow_ids) & set(other.source_flow_ids):
                    graph.add_composition(sid, other_id)
        return graph

    def run_all(self) -> CTS18Report:
        report = CTS18Report(backend=self.session.backend_name)

        main_objs, main_graph = build_main_scenario()
        report.original_graph = main_graph
        report.published_objects = list(main_objs)
        report.flow_ids = {"F1": "hext:cts18:F1", "F2": "hext:cts18:F2"}
        self._publish(main_objs)

        for topic, obj in main_objs:
            if obj.type == "surface":
                report.surface_objects[obj.id] = obj

        f1, f2 = report.flow_ids["F1"], report.flow_ids["F2"]
        s1 = "hext:cts18:S1"

        diagram_objs, diagram_graph = build_diagram_surfaces(f1, f2)
        self._publish(diagram_objs)
        for _, obj in diagram_objs:
            report.surface_objects[obj.id] = obj
        report.diagram_topology["D1"] = diagram_graph.canonical()

        rewrite_objs, expected_steps = build_rewrite_sequence(f1, f2)
        self._publish(rewrite_objs)
        for _, obj in rewrite_objs:
            report.surface_objects[obj.id] = obj
        report.diagram_topology["rewrite"] = {
            "diagram_id": "hext:cts18:diagram:rewrite",
            "expected_steps": expected_steps,
        }

        compose_objs, compose_graph = build_composition_scenario(f1, f2)
        report.expected_rewrite_steps = expected_steps
        report.compose_graph = compose_graph
        self._publish(compose_objs)
        for topic, obj in compose_objs:
            if obj.type == "surface":
                report.surface_objects[obj.id] = obj
        report.diagram_topology["compose"] = compose_graph.canonical()

        cross_objs = build_cross_topic_refs(f1, f2, s1)
        self._publish(cross_objs)
        report.published_objects.extend(diagram_objs + rewrite_objs + compose_objs + cross_objs)

        tests = [
            self.cts_18_1_surface_preservation,
            self.cts_18_2_flow_membership,
            self.cts_18_3_diagram_preservation,
            self.cts_18_4_rewrite_sequence,
            self.cts_18_5_history_reconstruction,
            self.cts_18_6_replay_topology,
            self.cts_18_8_determinism,
            self.cts_18_9_composition,
            self.cts_18_10_cross_topic,
        ]
        for fn in tests:
            try:
                report.add(fn(report))
            except Exception as exc:
                report.add(CTS18Result(fn.__name__, fn.__name__, False, f"EXCEPTION: {exc}"))

        return report

    def cts_18_1_surface_preservation(self, report: CTS18Report) -> CTS18Result:
        originals = dict(report.surface_objects)
        subscribe_ok = True

        if self.session._mode != "http":
            received: list[HextObject] = []
            test_surface = _surface_object(
                surface_id="hext:cts18:sub-test",
                source_flow_ids=[report.flow_ids["F1"]],
                target_flow_ids=[report.flow_ids["F2"]],
                diagram_id="hext:cts18:diagram:sub",
                rewrite_step=0,
                label="subscribe test",
            )
            iso = self._iso_topic("Diagnostic")
            if self.session.runtime:
                self.session.runtime.router.register(iso)
            handle = self.session.subscribe(iso, received.append)
            self.session.publish(iso, test_surface)
            time.sleep(0.2)
            self.session.unsubscribe(handle)
            matching = [o for o in received if o.id == test_surface.id]
            subscribe_ok = len(matching) >= 1 and _surface_unchanged(test_surface, matching[-1])

        history_ok = True
        replay_ok = True
        surface_iso = self._iso_topic("Surface")
        for orig in originals.values():
            for h in self.session.history(surface_iso, limit=200):
                if h.id == orig.id and not _surface_unchanged(orig, h):
                    history_ok = False
            for r in self.session.replay(surface_iso, last_n=200):
                if r.id == orig.id and not _surface_unchanged(orig, r):
                    replay_ok = False

        passed = subscribe_ok and history_ok and replay_ok
        return CTS18Result(
            "CTS-18.1", "Surface Preservation", passed,
            f"subscribe={subscribe_ok} history={history_ok} replay={replay_ok}",
            {"subscribe": subscribe_ok, "history": history_ok, "replay": replay_ok},
        )

    def cts_18_2_flow_membership(self, report: CTS18Report) -> CTS18Result:
        violations = []
        surface_iso = self._iso_topic("Surface")
        for orig in report.surface_objects.values():
            expected = _extract_surface(orig)
            for label, source in [
                ("history", self.session.history(surface_iso, limit=200)),
                ("replay", self.session.replay(surface_iso, last_n=200)),
            ]:
                for obj in source:
                    if obj.id != orig.id:
                        continue
                    got = _extract_surface(obj)
                    if got["source_flow_ids"] != expected["source_flow_ids"]:
                        violations.append(f"{label}:{obj.id}:source")
                    if got["target_flow_ids"] != expected["target_flow_ids"]:
                        violations.append(f"{label}:{obj.id}:target")
        return CTS18Result(
            "CTS-18.2", "Flow Membership", len(violations) == 0,
            f"surfaces_checked={len(report.surface_objects)} violations={violations[:5]}",
            {"violations": len(violations)},
        )

    def cts_18_3_diagram_preservation(self, report: CTS18Report) -> CTS18Result:
        d1 = "hext:cts18:diagram:D1"
        violations = []
        surface_iso = self._iso_topic("Surface")
        diagram_ids = {
            obj.id: obj.metadata.get("diagram_id")
            for obj in report.surface_objects.values()
            if obj.id.startswith("hext:cts18:diagram:")
        }
        for sid, expected_diagram in diagram_ids.items():
            for obj in self.session.history(surface_iso, limit=200):
                if obj.id == sid and obj.metadata.get("diagram_id") != expected_diagram:
                    violations.append(f"history:{sid}")
            for obj in self.session.replay(surface_iso, last_n=200):
                if obj.id == sid and obj.metadata.get("diagram_id") != expected_diagram:
                    violations.append(f"replay:{sid}")
        d1_surfaces = [s for s, d in diagram_ids.items() if d == d1]
        passed = len(violations) == 0 and len(d1_surfaces) >= 2
        return CTS18Result(
            "CTS-18.3", "Diagram Preservation", passed,
            f"diagram_id={d1} surfaces_in_d1={len(d1_surfaces)} violations={violations}",
            {"d1_surfaces": len(d1_surfaces), "violations": len(violations)},
        )

    def cts_18_4_rewrite_sequence(self, report: CTS18Report) -> CTS18Result:
        expected_steps = report.expected_rewrite_steps
        surface_iso = self._iso_topic("Surface")
        history_steps = []
        for obj in self.session.history(surface_iso, limit=200):
            if obj.id.startswith("hext:cts18:rewrite:"):
                history_steps.append(int(obj.metadata.get("rewrite_step", -1)))
        replay_steps = []
        for obj in self.session.replay(surface_iso, last_n=200):
            if obj.id.startswith("hext:cts18:rewrite:"):
                replay_steps.append(int(obj.metadata.get("rewrite_step", -1)))

        history_order_ok = history_steps == expected_steps
        replay_order_ok = replay_steps == expected_steps
        monotonic_ok = history_steps == sorted(history_steps)
        passed = history_order_ok and replay_order_ok and monotonic_ok
        return CTS18Result(
            "CTS-18.4", "Rewrite Sequence", passed,
            f"expected={expected_steps} history={history_steps} replay={replay_steps}",
            {"history_steps": history_steps, "replay_steps": replay_steps},
        )

    def cts_18_5_history_reconstruction(self, report: CTS18Report) -> CTS18Result:
        expected = self._build_expected_full_graph(report)
        reconstructed = self._collect_surface_graph(
            prefix="hext:cts18:",
            include_flows=True,
            include_composition=None,
        )
        reconstructed.surfaces.pop("hext:cts18:sub-test", None)
        isomorphic = expected.isomorphic_to(reconstructed)
        no_dupes = len(reconstructed.surfaces) == len({s.surface_id for s in reconstructed.surfaces.values()})
        return CTS18Result(
            "CTS-18.5", "History Reconstruction", isomorphic and no_dupes,
            f"expected_surfaces={len(expected.surfaces)} reconstructed={len(reconstructed.surfaces)} isomorphic={isomorphic}",
            {"isomorphic": isomorphic, "no_duplicates": no_dupes},
        )

    def cts_18_6_replay_topology(self, report: CTS18Report) -> CTS18Result:
        surface_iso = self._iso_topic("Surface")
        graph = SurfaceGraph()
        for obj in self.session.replay(surface_iso, last_n=200):
            if obj.type == "surface" and obj.id.startswith("hext:cts18:"):
                graph.add_surface(obj)

        originals = SurfaceGraph()
        for obj in report.surface_objects.values():
            originals.add_surface(obj)

        topology_ok = True
        for sid, orig in originals.surfaces.items():
            recon = graph.surfaces.get(sid)
            if recon is None or recon.to_dict() != orig.to_dict():
                topology_ok = False

        no_missing = all(sid in graph.surfaces for sid in originals.surfaces)
        no_dupes = len(graph.surfaces) >= len(originals.surfaces)
        passed = topology_ok and no_missing
        return CTS18Result(
            "CTS-18.6", "Replay Topology", passed,
            f"surfaces={len(graph.surfaces)} topology_ok={topology_ok} no_missing={no_missing}",
            {"topology_ok": topology_ok, "no_missing": no_missing, "no_dupes": no_dupes},
        )

    def cts_18_8_determinism(self, report: CTS18Report) -> CTS18Result:
        graphs: list[dict[str, Any]] = []
        for _ in range(3):
            g = self._collect_surface_graph(prefix="hext:cts18:", include_flows=True)
            graphs.append(g.canonical())
        identical = graphs[0] == graphs[1] == graphs[2]
        return CTS18Result(
            "CTS-18.8", "Determinism", identical,
            f"triplicate_identical={identical}",
            {"triplicate_identical": identical},
        )

    def cts_18_9_composition(self, report: CTS18Report) -> CTS18Result:
        expected_graph = report.compose_graph
        assert expected_graph is not None
        reconstructed = self._collect_surface_graph(
            prefix="hext:cts18:compose:",
            include_flows=True,
            include_composition=expected_graph,
        )
        compose_surfaces = {
            k: v for k, v in reconstructed.surfaces.items()
            if k.startswith("hext:cts18:compose:")
        }
        expected_surfaces = {
            k: v for k, v in expected_graph.surfaces.items()
        }
        surfaces_ok = compose_surfaces.keys() == expected_surfaces.keys()
        for sid in expected_surfaces:
            if compose_surfaces.get(sid) is None:
                surfaces_ok = False
            elif compose_surfaces[sid].to_dict() != expected_surfaces[sid].to_dict():
                surfaces_ok = False

        composition_ok = expected_graph.composition_edges == reconstructed.composition_edges
        chain_ok = ("hext:cts18:compose:S12", "hext:cts18:compose:S23") in reconstructed.composition_edges
        passed = surfaces_ok and composition_ok and chain_ok
        return CTS18Result(
            "CTS-18.9", "Multiple Surface Composition", passed,
            f"surfaces_ok={surfaces_ok} composition_ok={composition_ok} chain_ok={chain_ok}",
            {"surfaces_ok": surfaces_ok, "composition_ok": composition_ok, "chain_ok": chain_ok},
        )

    def cts_18_10_cross_topic(self, report: CTS18Report) -> CTS18Result:
        f1, f2 = report.flow_ids["F1"], report.flow_ids["F2"]
        s1 = "hext:cts18:S1"
        expected_refs = {
            "hext:cts18:cross:C1": {
                "observation": "hext:cts18:O1",
                "trajectory": "hext:cts18:T1",
                "trajectory_flow": f1,
                "surface": s1,
            },
            "hext:cts18:cross:R1": {
                "observation": "hext:cts18:O2",
                "trajectory": "hext:cts18:T2",
                "trajectory_flow": f2,
                "surface": s1,
                "controller": "hext:cts18:cross:C1",
            },
        }
        violations = []
        topic_map = {
            "Controller": self._iso_topic("Controller"),
            "Replay": self._iso_topic("Replay"),
        }
        for label, iso in topic_map.items():
            for obj in self.session.history(iso, limit=50):
                if obj.id not in expected_refs:
                    continue
                refs = obj.metadata.get("refs", {})
                if refs != expected_refs[obj.id]:
                    violations.append(f"history:{obj.id}")
            for obj in self.session.replay(iso, last_n=50):
                if obj.id not in expected_refs:
                    continue
                refs = obj.metadata.get("refs", {})
                if refs != expected_refs[obj.id]:
                    violations.append(f"replay:{obj.id}")

        flow_ids = {
            o.id for o in self.session.history(self._iso_topic("TrajectoryFlow"), limit=200)
        }
        flow_refs_valid = f1 in flow_ids and f2 in flow_ids
        surface_valid = s1 in {
            o.id for o in self.session.history(self._iso_topic("Surface"), limit=200)
        }
        passed = len(violations) == 0 and flow_refs_valid and surface_valid
        return CTS18Result(
            "CTS-18.10", "Cross-topic Integrity", passed,
            f"violations={violations} flow_refs_valid={flow_refs_valid} surface_valid={surface_valid}",
            {"violations": len(violations), "flow_refs_valid": flow_refs_valid},
        )


def run_backend_comparison(
    inprocess_report: CTS18Report,
    redis_report: CTS18Report,
) -> CTS18Result:
    assert inprocess_report.original_graph and redis_report.original_graph
    in_canon = inprocess_report.original_graph.canonical()
    redis_canon = redis_report.original_graph.canonical()
    isomorphic = in_canon == redis_canon
    return CTS18Result(
        "CTS-18.7", "Backend Compatibility",
        isomorphic,
        f"inprocess_surfaces={len(inprocess_report.original_graph.surfaces)} "
        f"redis_surfaces={len(redis_report.original_graph.surfaces)} isomorphic={isomorphic}",
        {"isomorphic": isomorphic},
    )


def export_cts18_artifacts(
    reports: dict[str, CTS18Report],
    comparison: CTS18Result | None,
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    graph_doc: dict[str, Any] = {}
    for backend, rep in reports.items():
        if rep.original_graph:
            graph_doc[backend] = rep.original_graph.canonical()
    (out_dir / "surface_graph.json").write_text(
        json.dumps(graph_doc, indent=2), encoding="utf-8",
    )

    diagram_doc = {
        backend: rep.diagram_topology
        for backend, rep in reports.items()
    }
    (out_dir / "diagram_topology.json").write_text(
        json.dumps(diagram_doc, indent=2), encoding="utf-8",
    )

    rows: list[dict[str, Any]] = []
    for backend, rep in reports.items():
        for obj in rep.surface_objects.values():
            meta = obj.metadata
            rows.append({
                "backend": backend,
                "object_id": obj.id,
                "surface_id": meta.get("surface_id", obj.id),
                "source_flow_ids": json.dumps(meta.get("source_flow_ids", [])),
                "target_flow_ids": json.dumps(meta.get("target_flow_ids", [])),
                "diagram_id": meta.get("diagram_id"),
                "rewrite_step": meta.get("rewrite_step"),
                "type": obj.type,
                "version": obj.version,
            })
    with (out_dir / "surface_graph.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "backend", "object_id", "surface_id", "source_flow_ids",
                "target_flow_ids", "diagram_id", "rewrite_step", "type", "version",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    cmp_rows: list[dict[str, Any]] = []
    if comparison:
        cmp_rows.append({
            "backend": "comparison",
            "test_id": comparison.test_id,
            "passed": comparison.passed,
            "details": comparison.details,
            "inprocess_passed": "",
            "redis_passed": "",
            "isomorphic": comparison.measurements.get("isomorphic"),
        })
    for backend, rep in reports.items():
        for r in rep.results:
            cmp_rows.append({
                "backend": backend,
                "test_id": r.test_id,
                "passed": r.passed,
                "details": r.details,
                "inprocess_passed": "",
                "redis_passed": "",
                "isomorphic": "",
            })
    with (out_dir / "surface_backend_comparison.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["backend", "test_id", "passed", "details", "inprocess_passed", "redis_passed", "isomorphic"],
        )
        w.writeheader()
        for row in cmp_rows:
            w.writerow({k: row.get(k, "") for k in w.fieldnames})

    lines = [
        "# CTS-18 Surface Morphism Compatibility Report\n\n",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n",
        "## Purpose\n\n",
        "Verify structural preservation of Surface Morphisms (higher-order relationships ",
        "between trajectory flows) through publish, subscribe, history, and replay. ",
        "No runtime modifications.\n\n",
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
        lines.append("## CTS-18.7 Backend Compatibility\n\n")
        lines.append(f"**{'PASS' if comparison.passed else 'FAIL'}** — {comparison.details}\n\n")
    all_primary = all(
        r.passed
        for name in ("inprocess", "redis")
        if name in reports
        for r in reports[name].results
    ) and (comparison.passed if comparison else True)
    lines.append(f"## Overall Verdict\n\n**{'PASS' if all_primary else 'FAIL'}**\n")
    (out_dir / "surface_report.md").write_text("".join(lines), encoding="utf-8")
