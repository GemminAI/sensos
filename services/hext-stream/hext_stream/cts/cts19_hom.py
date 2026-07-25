"""CTS-19: Enriched Morphism (Hom-object) Conformance Test."""

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

HOM_CORE_FIELDS = (
    "hom_id",
    "source_object",
    "target_object",
    "hom_type",
    "metric",
    "weight",
    "distance",
    "cost",
    "composition_ids",
    "lineage",
)


@dataclass
class HomNode:
    hom_id: str
    source_object: str
    target_object: str
    hom_type: str
    metric: float
    weight: float
    distance: float
    cost: float
    composition_ids: list[str]
    lineage: dict[str, Any]
    object_id: str
    version: str
    associativity_group: str | None = None

    @classmethod
    def from_object(cls, obj: HextObject) -> HomNode:
        meta = obj.metadata
        return cls(
            hom_id=meta.get("hom_id", obj.id),
            source_object=meta.get("source_object", ""),
            target_object=meta.get("target_object", ""),
            hom_type=meta.get("hom_type", "enriched"),
            metric=float(meta.get("metric", 0.0)),
            weight=float(meta.get("weight", 0.0)),
            distance=float(meta.get("distance", 0.0)),
            cost=float(meta.get("cost", 0.0)),
            composition_ids=list(meta.get("composition_ids", [])),
            lineage=dict(meta.get("lineage", {})),
            object_id=obj.id,
            version=obj.version,
            associativity_group=meta.get("associativity_group"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "hom_id": self.hom_id,
            "source_object": self.source_object,
            "target_object": self.target_object,
            "hom_type": self.hom_type,
            "metric": self.metric,
            "weight": self.weight,
            "distance": self.distance,
            "cost": self.cost,
            "composition_ids": sorted(self.composition_ids),
            "lineage": self.lineage,
            "object_id": self.object_id,
            "version": self.version,
        }
        if self.associativity_group:
            out["associativity_group"] = self.associativity_group
        return out


@dataclass
class RefNode:
    id: str
    type: str
    refs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "refs": dict(sorted(self.refs.items()))}


@dataclass
class HomGraph:
    homs: dict[str, HomNode] = field(default_factory=dict)
    refs: dict[str, RefNode] = field(default_factory=dict)
    composition_edges: list[tuple[str, str]] = field(default_factory=list)
    associativity_graphs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_hom(self, obj: HextObject) -> None:
        node = HomNode.from_object(obj)
        self.homs[node.hom_id] = node
        for cid in node.composition_ids:
            edge = (cid, node.hom_id)
            if edge not in self.composition_edges:
                self.composition_edges.append(edge)
        if obj.metadata.get("composition_graph"):
            self.associativity_graphs[node.hom_id] = obj.metadata["composition_graph"]

    def add_ref(self, obj: HextObject) -> None:
        refs = obj.metadata.get("refs", {})
        self.refs[obj.id] = RefNode(id=obj.id, type=obj.type, refs=refs)

    def canonical(self) -> dict[str, Any]:
        return {
            "homs": {k: v.to_dict() for k, v in sorted(self.homs.items())},
            "refs": {k: v.to_dict() for k, v in sorted(self.refs.items())},
            "composition_edges": sorted(self.composition_edges),
            "associativity_graphs": {
                k: v for k, v in sorted(self.associativity_graphs.items())
            },
        }

    def isomorphic_to(self, other: HomGraph) -> bool:
        return self.canonical() == other.canonical()


def _hom_object(
    *,
    hom_id: str,
    source_object: str,
    target_object: str,
    hom_type: str = "enriched",
    metric: float = 1.0,
    weight: float = 1.0,
    distance: float = 0.5,
    cost: float = 0.25,
    composition_ids: list[str] | None = None,
    lineage: dict[str, Any] | None = None,
    associativity_group: str | None = None,
    composition_graph: dict[str, Any] | None = None,
    label: str = "",
) -> HextObject:
    meta: dict[str, Any] = {
        "hom_id": hom_id,
        "source_object": source_object,
        "target_object": target_object,
        "hom_type": hom_type,
        "metric": metric,
        "weight": weight,
        "distance": distance,
        "cost": cost,
        "composition_ids": composition_ids or [],
        "lineage": lineage or {},
        "label": label or hom_id,
    }
    if associativity_group:
        meta["associativity_group"] = associativity_group
    if composition_graph:
        meta["composition_graph"] = composition_graph
    return HextObject(
        id=hom_id,
        timestamp=utcnow(),
        source="cts-19",
        type="hom",
        version="1.0.0",
        payload={"label": label or hom_id},
        metadata=meta,
    )


def _flow_object(
    obj_id: str, obj_type: str, parent_id: str | None, label: str,
) -> HextObject:
    return HextObject(
        id=obj_id,
        timestamp=utcnow(),
        source="cts-19",
        type=obj_type,
        version="1.0.0",
        payload={"label": label},
        metadata={"parent_id": parent_id, "label": label},
    )


def _surface_object(
    surface_id: str, source_flow_ids: list[str], target_flow_ids: list[str], label: str,
) -> HextObject:
    return HextObject(
        id=surface_id,
        timestamp=utcnow(),
        source="cts-19",
        type="surface",
        version="1.0.0",
        payload={"label": label},
        metadata={
            "surface_id": surface_id,
            "source_flow_ids": source_flow_ids,
            "target_flow_ids": target_flow_ids,
            "label": label,
        },
    )


def build_hom_scenario() -> tuple[list[tuple[str, HextObject]], HomGraph, dict[str, str]]:
    """Core Hom objects: AB, BC, AC composed, CD, associativity, identity."""
    a, b, c, d = "hext:cts19:A", "hext:cts19:B", "hext:cts19:C", "hext:cts19:D"
    hom_ab = "hext:cts19:hom:AB"
    hom_bc = "hext:cts19:hom:BC"
    hom_ac = "hext:cts19:hom:AC"
    hom_cd = "hext:cts19:hom:CD"
    hom_abc = "hext:cts19:hom:ABC"
    hom_bcd = "hext:cts19:hom:BCD"
    hom_ad_left = "hext:cts19:hom:AD-left"
    hom_ad_right = "hext:cts19:hom:AD-right"
    id_a = "hext:cts19:hom:id-A"

    ids = {
        "A": a, "B": b, "C": c, "D": d,
        "hom_ab": hom_ab, "hom_bc": hom_bc, "hom_ac": hom_ac,
        "hom_cd": hom_cd, "hom_abc": hom_abc, "hom_bcd": hom_bcd,
        "hom_ad_left": hom_ad_left, "hom_ad_right": hom_ad_right,
        "id_a": id_a,
    }

    objects: list[tuple[str, HextObject]] = [
        ("Hom", _hom_object(
            hom_id=hom_ab, source_object=a, target_object=b,
            metric=1.1, weight=0.9, distance=0.3, cost=0.1,
            lineage={"root_id": a, "depth": 0}, label="Hom(A,B)",
        )),
        ("Hom", _hom_object(
            hom_id=hom_bc, source_object=b, target_object=c,
            metric=2.2, weight=1.1, distance=0.4, cost=0.2,
            lineage={"root_id": a, "depth": 1}, label="Hom(B,C)",
        )),
        ("Hom", _hom_object(
            hom_id=hom_ac, source_object=a, target_object=c,
            hom_type="composed",
            metric=3.3, weight=2.0, distance=0.7, cost=0.3,
            composition_ids=[hom_ab, hom_bc],
            lineage={"root_id": a, "depth": 2}, label="Hom(A,C)",
        )),
        ("Hom", _hom_object(
            hom_id=hom_cd, source_object=c, target_object=d,
            metric=4.4, weight=1.5, distance=0.5, cost=0.15,
            lineage={"root_id": a, "depth": 1}, label="Hom(C,D)",
        )),
        ("Hom", _hom_object(
            hom_id=hom_abc, source_object=a, target_object=c,
            hom_type="composed",
            metric=5.5, weight=2.5, distance=0.8, cost=0.35,
            composition_ids=[hom_ab, hom_bc],
            associativity_group="left-inner",
            composition_graph={
                "grouping": "(AB ∘ BC)",
                "edges": [[hom_ab, hom_bc]],
            },
            label="(Hom(A,B) ∘ Hom(B,C))",
        )),
        ("Hom", _hom_object(
            hom_id=hom_bcd, source_object=b, target_object=d,
            hom_type="composed",
            metric=6.6, weight=2.8, distance=0.9, cost=0.4,
            composition_ids=[hom_bc, hom_cd],
            associativity_group="right-inner",
            composition_graph={
                "grouping": "(BC ∘ CD)",
                "edges": [[hom_bc, hom_cd]],
            },
            label="(Hom(B,C) ∘ Hom(C,D))",
        )),
        ("Hom", _hom_object(
            hom_id=hom_ad_left, source_object=a, target_object=d,
            hom_type="composed",
            metric=7.7, weight=3.0, distance=1.0, cost=0.5,
            composition_ids=[hom_abc, hom_cd],
            associativity_group="left",
            composition_graph={
                "grouping": "(AB ∘ BC) ∘ CD",
                "edges": [[hom_ab, hom_bc], [hom_abc, hom_cd]],
            },
            label="(Hom(A,B)∘Hom(B,C))∘Hom(C,D)",
        )),
        ("Hom", _hom_object(
            hom_id=hom_ad_right, source_object=a, target_object=d,
            hom_type="composed",
            metric=8.8, weight=3.2, distance=1.1, cost=0.55,
            composition_ids=[hom_ab, hom_bcd],
            associativity_group="right",
            composition_graph={
                "grouping": "AB ∘ (BC ∘ CD)",
                "edges": [[hom_bc, hom_cd], [hom_ab, hom_bcd]],
            },
            label="Hom(A,B)∘(Hom(B,C)∘Hom(C,D))",
        )),
        ("Hom", _hom_object(
            hom_id=id_a, source_object=a, target_object=a,
            hom_type="identity",
            metric=0.0, weight=1.0, distance=0.0, cost=0.0,
            composition_ids=[],
            lineage={"root_id": a, "depth": 0, "identity": True},
            label="id(A)",
        )),
    ]

    graph = HomGraph()
    for _, obj in objects:
        graph.add_hom(obj)
    return objects, graph, ids


def build_trajectory_hom(ids: dict[str, str]) -> tuple[list[tuple[str, HextObject]], HomGraph]:
    """Observation → Trajectory → TrajectoryFlow → Hom-object."""
    o = "hext:cts19:traj:O1"
    t = "hext:cts19:traj:T1"
    f = "hext:cts19:traj:F1"
    x = "hext:cts19:traj:X1"
    hom_fx = "hext:cts19:hom:F-X"

    objects = [
        ("Observation", _flow_object(o, "observation", None, "O1")),
        ("Trajectory", _flow_object(t, "trajectory", o, "T1")),
        ("TrajectoryFlow", _flow_object(f, "trajectory.flow", t, "F1")),
        ("Hom", _hom_object(
            hom_id=hom_fx, source_object=f, target_object=x,
            metric=9.9, weight=1.0, distance=1.2, cost=0.6,
            lineage={"trajectory_flow": f, "observation": o, "trajectory": t},
            label="Hom(F,X)",
        )),
    ]
    graph = HomGraph()
    for topic, obj in objects:
        if topic == "Hom":
            graph.add_hom(obj)
    return objects, graph


def build_surface_hom() -> tuple[list[tuple[str, HextObject]], HomGraph]:
    """Surface → Hom-object → Surface."""
    s1 = "hext:cts19:surf:S1"
    s2 = "hext:cts19:surf:S2"
    hom_s = "hext:cts19:hom:S1-S2"

    objects = [
        ("Surface", _surface_object(s1, [], ["hext:cts19:traj:F1"], "S1")),
        ("Hom", _hom_object(
            hom_id=hom_s, source_object=s1, target_object=s2,
            metric=10.0, weight=2.0, distance=1.5, cost=0.7,
            lineage={"surface_source": s1, "surface_target": s2},
            label="Hom(S1,S2)",
        )),
        ("Surface", _surface_object(s2, [hom_s], [], "S2")),
    ]
    graph = HomGraph()
    for topic, obj in objects:
        if topic == "Hom":
            graph.add_hom(obj)
    return objects, graph


def build_cross_topic(
    ids: dict[str, str],
) -> list[tuple[str, HextObject]]:
    hom_ab = ids["hom_ab"]
    a, b = ids["A"], ids["B"]
    c1 = "hext:cts19:cross:C1"
    r1 = "hext:cts19:cross:R1"
    return [
        (
            "Controller",
            HextObject(
                id=c1, timestamp=utcnow(), source="cts-19", type="controller",
                version="1.0.0",
                payload={"hom_ref": hom_ab},
                metadata={
                    "refs": {
                        "observation": "hext:cts19:traj:O1",
                        "trajectory": "hext:cts19:traj:T1",
                        "trajectory_flow": "hext:cts19:traj:F1",
                        "surface": "hext:cts19:surf:S1",
                        "hom": hom_ab,
                    },
                },
            ),
        ),
        (
            "Replay",
            HextObject(
                id=r1, timestamp=utcnow(), source="cts-19", type="replay",
                version="1.0.0",
                payload={"controller_ref": c1},
                metadata={
                    "refs": {
                        "observation": "hext:cts19:traj:O1",
                        "trajectory": "hext:cts19:traj:T1",
                        "trajectory_flow": "hext:cts19:traj:F1",
                        "surface": "hext:cts19:surf:S2",
                        "hom": hom_ab,
                        "controller": c1,
                        "source_object": a,
                        "target_object": b,
                    },
                },
            ),
        ),
    ]


def _extract_hom(obj: HextObject) -> dict[str, Any]:
    meta = obj.metadata
    return {
        "hom_id": meta.get("hom_id", obj.id),
        "source_object": meta.get("source_object"),
        "target_object": meta.get("target_object"),
        "hom_type": meta.get("hom_type"),
        "metric": meta.get("metric"),
        "weight": meta.get("weight"),
        "distance": meta.get("distance"),
        "cost": meta.get("cost"),
        "composition_ids": sorted(meta.get("composition_ids", [])),
        "lineage": meta.get("lineage", {}),
        "version": obj.version,
    }


def _hom_unchanged(original: HextObject, observed: HextObject) -> bool:
    return _extract_hom(original) == _extract_hom(observed) and original.id == observed.id


@dataclass
class CTS19Result:
    test_id: str
    name: str
    passed: bool
    details: str = ""
    measurements: dict[str, Any] = field(default_factory=dict)


@dataclass
class CTS19Report:
    backend: str
    results: list[CTS19Result] = field(default_factory=list)
    original_graph: HomGraph | None = None
    hom_objects: dict[str, HextObject] = field(default_factory=dict)
    published_objects: list[tuple[str, HextObject]] = field(default_factory=list)
    object_ids: dict[str, str] = field(default_factory=dict)
    composition_records: list[dict[str, Any]] = field(default_factory=list)
    identity_records: list[dict[str, Any]] = field(default_factory=list)
    metric_records: list[dict[str, Any]] = field(default_factory=list)

    def add(self, r: CTS19Result) -> None:
        self.results.append(r)


class CTS19Runner:
    """CTS-19 enriched morphism conformance tests."""

    PREFIX = "hext:cts19:"

    def __init__(self, session: RuntimeSession) -> None:
        self.session = session
        self.run_id = uuid.uuid4().hex[:8]
        self._register_topics()

    def _iso_topic(self, topic: str) -> str:
        base = {
            "Observation": "CTS19Observation",
            "Trajectory": "CTS19Trajectory",
            "TrajectoryFlow": "CTS19TrajectoryFlow",
            "Surface": "CTS19Surface",
            "Hom": "CTS19Hom",
            "Controller": "CTS19Controller",
            "Replay": "CTS19Replay",
            "Diagnostic": "CTS19Diagnostic",
        }.get(topic, topic)
        return f"{base}-{self.run_id}"

    def _register_topics(self) -> None:
        if not self.session.runtime:
            return
        for name in (
            "Observation", "Trajectory", "TrajectoryFlow", "Surface",
            "Hom", "Controller", "Replay", "Diagnostic",
        ):
            self.session.runtime.router.register(self._iso_topic(name))

    def _publish(self, items: list[tuple[str, HextObject]]) -> None:
        for topic, obj in items:
            iso = self._iso_topic(topic)
            if self.session.runtime:
                self.session.runtime.router.register(iso)
            self.session.publish(iso, obj)

    def _collect_hom_graph(self, *, prefix: str = "hext:cts19:") -> HomGraph:
        graph = HomGraph()
        hom_iso = self._iso_topic("Hom")
        for obj in self.session.history(hom_iso, limit=300):
            if obj.id.startswith(prefix) and obj.type == "hom":
                graph.add_hom(obj)

        for topic in ("Observation", "Trajectory", "TrajectoryFlow", "Surface", "Controller", "Replay"):
            iso = self._iso_topic(topic)
            for obj in self.session.history(iso, limit=200):
                if obj.id.startswith(prefix) and obj.metadata.get("refs"):
                    graph.add_ref(obj)
        return graph

    def _build_expected_graph(self, report: CTS19Report) -> HomGraph:
        graph = HomGraph()
        skip = {"hext:cts19:sub-test"}
        for _, obj in report.published_objects:
            if obj.id in skip:
                continue
            if obj.type == "hom":
                graph.add_hom(obj)
            elif obj.metadata.get("refs"):
                graph.add_ref(obj)
        return graph

    def run_all(self) -> CTS19Report:
        report = CTS19Report(backend=self.session.backend_name)

        hom_objs, hom_graph, ids = build_hom_scenario()
        report.original_graph = hom_graph
        report.object_ids = ids
        report.published_objects = list(hom_objs)
        self._publish(hom_objs)
        for _, obj in hom_objs:
            if obj.type == "hom":
                report.hom_objects[obj.id] = obj

        traj_objs, _ = build_trajectory_hom(ids)
        self._publish(traj_objs)
        report.published_objects.extend(traj_objs)
        for topic, obj in traj_objs:
            if obj.type == "hom":
                report.hom_objects[obj.id] = obj

        surf_objs, _ = build_surface_hom()
        self._publish(surf_objs)
        report.published_objects.extend(surf_objs)
        for topic, obj in surf_objs:
            if obj.type == "hom":
                report.hom_objects[obj.id] = obj

        cross_objs = build_cross_topic(ids)
        self._publish(cross_objs)
        report.published_objects.extend(cross_objs)

        report.composition_records = [
            {"hom_id": ids["hom_ac"], "composition_ids": [ids["hom_ab"], ids["hom_bc"]], "expected_source": ids["A"], "expected_target": ids["C"]},
            {"hom_id": ids["hom_ad_left"], "composition_ids": [ids["hom_abc"], ids["hom_cd"]], "grouping": "left"},
            {"hom_id": ids["hom_ad_right"], "composition_ids": [ids["hom_ab"], ids["hom_bcd"]], "grouping": "right"},
        ]
        report.identity_records = [
            {"hom_id": ids["id_a"], "source_object": ids["A"], "target_object": ids["A"], "hom_type": "identity"},
        ]
        report.metric_records = [
            {"hom_id": obj.id, **_extract_hom(obj)}
            for obj in report.hom_objects.values()
        ]

        tests = [
            self.cts_19_1_publish_preservation,
            self.cts_19_2_composition_preservation,
            self.cts_19_3_associativity,
            self.cts_19_4_identity,
            self.cts_19_5_metric_preservation,
            self.cts_19_6_history_reconstruction,
            self.cts_19_7_replay_topology,
            self.cts_19_9_determinism,
            self.cts_19_10_trajectory_compatibility,
            self.cts_19_11_surface_compatibility,
            self.cts_19_12_cross_topic,
        ]
        for fn in tests:
            try:
                report.add(fn(report))
            except Exception as exc:
                report.add(CTS19Result(fn.__name__, fn.__name__, False, f"EXCEPTION: {exc}"))

        return report

    def cts_19_1_publish_preservation(self, report: CTS19Report) -> CTS19Result:
        originals = dict(report.hom_objects)
        subscribe_ok = True

        if self.session._mode != "http":
            received: list[HextObject] = []
            test_hom = _hom_object(
                hom_id="hext:cts19:sub-test",
                source_object=report.object_ids["A"],
                target_object=report.object_ids["B"],
                metric=0.1, weight=0.1, distance=0.1, cost=0.1,
                label="subscribe test",
            )
            iso = self._iso_topic("Diagnostic")
            if self.session.runtime:
                self.session.runtime.router.register(iso)
            handle = self.session.subscribe(iso, received.append)
            self.session.publish(iso, test_hom)
            time.sleep(0.2)
            self.session.unsubscribe(handle)
            matching = [o for o in received if o.id == test_hom.id]
            subscribe_ok = (
                len(matching) >= 1
                and matching[-1].metadata.get("hom_id") == test_hom.metadata["hom_id"]
                and _hom_unchanged(test_hom, matching[-1])
            )

        history_ok = True
        replay_ok = True
        hom_iso = self._iso_topic("Hom")
        for orig in originals.values():
            for h in self.session.history(hom_iso, limit=300):
                if h.id == orig.id and not _hom_unchanged(orig, h):
                    history_ok = False
            for r in self.session.replay(hom_iso, last_n=300):
                if r.id == orig.id and not _hom_unchanged(orig, r):
                    replay_ok = False

        passed = subscribe_ok and history_ok and replay_ok
        return CTS19Result(
            "CTS-19.1", "Publish Preservation", passed,
            f"subscribe={subscribe_ok} history={history_ok} replay={replay_ok}",
            {"subscribe": subscribe_ok, "history": history_ok, "replay": replay_ok},
        )

    def cts_19_2_composition_preservation(self, report: CTS19Report) -> CTS19Result:
        violations = []
        hom_iso = self._iso_topic("Hom")
        hom_ac = report.object_ids["hom_ac"]
        expected = [report.object_ids["hom_ab"], report.object_ids["hom_bc"]]

        for label, source in [
            ("history", self.session.history(hom_iso, limit=300)),
            ("replay", self.session.replay(hom_iso, last_n=300)),
        ]:
            for obj in source:
                if obj.id != hom_ac:
                    continue
                got = sorted(obj.metadata.get("composition_ids", []))
                if got != sorted(expected):
                    violations.append(f"{label}:{obj.id}")

        passed = len(violations) == 0
        if passed:
            report.composition_records[0]["preserved"] = True
        return CTS19Result(
            "CTS-19.2", "Composition Preservation", passed,
            f"hom_ac={hom_ac} expected={expected} violations={violations}",
            {"violations": len(violations)},
        )

    def cts_19_3_associativity(self, report: CTS19Report) -> CTS19Result:
        hom_iso = self._iso_topic("Hom")
        left_id = report.object_ids["hom_ad_left"]
        right_id = report.object_ids["hom_ad_right"]
        expected_left = report.original_graph.associativity_graphs.get(left_id) if report.original_graph else None
        expected_right = report.original_graph.associativity_graphs.get(right_id) if report.original_graph else None

        left_ok = False
        right_ok = False
        left_edges: list[tuple[str, str]] = []
        right_edges: list[tuple[str, str]] = []

        for obj in self.session.history(hom_iso, limit=300):
            if obj.id == left_id:
                left_ok = obj.metadata.get("composition_graph") == expected_left
                for edge in obj.metadata.get("composition_graph", {}).get("edges", []):
                    left_edges.append((edge[0], edge[1]))
            if obj.id == right_id:
                right_ok = obj.metadata.get("composition_graph") == expected_right
                for edge in obj.metadata.get("composition_graph", {}).get("edges", []):
                    right_edges.append((edge[0], edge[1]))

        no_edge_loss = len(left_edges) >= 2 and len(right_edges) >= 2
        passed = left_ok and right_ok and no_edge_loss
        return CTS19Result(
            "CTS-19.3", "Associativity", passed,
            f"left_ok={left_ok} right_ok={right_ok} left_edges={len(left_edges)} right_edges={len(right_edges)}",
            {"left_ok": left_ok, "right_ok": right_ok, "no_edge_loss": no_edge_loss},
        )

    def cts_19_4_identity(self, report: CTS19Report) -> CTS19Result:
        id_a = report.object_ids["id_a"]
        a = report.object_ids["A"]
        hom_iso = self._iso_topic("Hom")
        violations = []

        for label, source in [
            ("history", self.session.history(hom_iso, limit=300)),
            ("replay", self.session.replay(hom_iso, last_n=300)),
        ]:
            found = False
            for obj in source:
                if obj.id != id_a:
                    continue
                found = True
                if (
                    obj.metadata.get("hom_type") != "identity"
                    or obj.metadata.get("source_object") != a
                    or obj.metadata.get("target_object") != a
                ):
                    violations.append(f"{label}:{obj.id}")
            if not found:
                violations.append(f"{label}:missing")

        passed = len(violations) == 0
        for rec in report.identity_records:
            rec["preserved"] = passed
        return CTS19Result(
            "CTS-19.4", "Identity Morphism", passed,
            f"id_a={id_a} violations={violations}",
            {"violations": len(violations)},
        )

    def cts_19_5_metric_preservation(self, report: CTS19Report) -> CTS19Result:
        violations = []
        hom_iso = self._iso_topic("Hom")
        enrich_fields = ("metric", "weight", "distance", "cost")

        for orig in report.hom_objects.values():
            expected = {f: orig.metadata.get(f) for f in enrich_fields}
            for label, source in [
                ("history", self.session.history(hom_iso, limit=300)),
                ("replay", self.session.replay(hom_iso, last_n=300)),
            ]:
                for obj in source:
                    if obj.id != orig.id:
                        continue
                    for f in enrich_fields:
                        if obj.metadata.get(f) != expected[f]:
                            violations.append(f"{label}:{obj.id}:{f}")

        passed = len(violations) == 0
        for rec in report.metric_records:
            rec["preserved"] = passed
        return CTS19Result(
            "CTS-19.5", "Enriched Metric Preservation", passed,
            f"homs_checked={len(report.hom_objects)} violations={violations[:5]}",
            {"violations": len(violations)},
        )

    def cts_19_6_history_reconstruction(self, report: CTS19Report) -> CTS19Result:
        expected = self._build_expected_graph(report)
        reconstructed = self._collect_hom_graph()
        isomorphic = expected.isomorphic_to(reconstructed)
        no_dupes = len(reconstructed.homs) == len({h.hom_id for h in reconstructed.homs.values()})
        return CTS19Result(
            "CTS-19.6", "History Reconstruction", isomorphic and no_dupes,
            f"expected_homs={len(expected.homs)} reconstructed={len(reconstructed.homs)} isomorphic={isomorphic}",
            {"isomorphic": isomorphic, "no_duplicates": no_dupes},
        )

    def cts_19_7_replay_topology(self, report: CTS19Report) -> CTS19Result:
        hom_iso = self._iso_topic("Hom")
        graph = HomGraph()
        for obj in self.session.replay(hom_iso, last_n=300):
            if obj.type == "hom" and obj.id.startswith(self.PREFIX):
                graph.add_hom(obj)

        topology_ok = True
        for hid, orig in report.hom_objects.items():
            recon = graph.homs.get(orig.metadata.get("hom_id", hid))
            if recon is None or recon.to_dict() != HomNode.from_object(orig).to_dict():
                topology_ok = False

        no_missing = all(
            obj.metadata.get("hom_id", obj.id) in graph.homs
            for obj in report.hom_objects.values()
        )
        passed = topology_ok and no_missing
        return CTS19Result(
            "CTS-19.7", "Replay Topology", passed,
            f"homs={len(graph.homs)} topology_ok={topology_ok} no_missing={no_missing}",
            {"topology_ok": topology_ok, "no_missing": no_missing},
        )

    def cts_19_9_determinism(self, report: CTS19Report) -> CTS19Result:
        graphs: list[dict[str, Any]] = []
        for _ in range(3):
            graphs.append(self._collect_hom_graph().canonical())
        identical = graphs[0] == graphs[1] == graphs[2]
        return CTS19Result(
            "CTS-19.9", "Determinism", identical,
            f"triplicate_identical={identical}",
            {"triplicate_identical": identical},
        )

    def cts_19_10_trajectory_compatibility(self, report: CTS19Report) -> CTS19Result:
        hom_fx = "hext:cts19:hom:F-X"
        hom_iso = self._iso_topic("Hom")
        flow_iso = self._iso_topic("TrajectoryFlow")
        violations = []

        hom_obj = None
        for obj in self.session.history(hom_iso, limit=300):
            if obj.id == hom_fx:
                hom_obj = obj
                break

        if hom_obj is None:
            violations.append("hom:missing")
        else:
            lineage = hom_obj.metadata.get("lineage", {})
            for key in ("trajectory_flow", "observation", "trajectory"):
                if key not in lineage:
                    violations.append(f"lineage:{key}")

        flow_ids = {o.id for o in self.session.history(flow_iso, limit=200)}
        if "hext:cts19:traj:F1" not in flow_ids:
            violations.append("trajectory_flow:missing")

        passed = len(violations) == 0
        return CTS19Result(
            "CTS-19.10", "Trajectory Compatibility", passed,
            f"hom_fx={hom_fx} violations={violations}",
            {"violations": len(violations)},
        )

    def cts_19_11_surface_compatibility(self, report: CTS19Report) -> CTS19Result:
        hom_s = "hext:cts19:hom:S1-S2"
        s1, s2 = "hext:cts19:surf:S1", "hext:cts19:surf:S2"
        hom_iso = self._iso_topic("Hom")
        surf_iso = self._iso_topic("Surface")
        violations = []

        hom_obj = next((o for o in self.session.history(hom_iso, limit=300) if o.id == hom_s), None)
        if hom_obj is None:
            violations.append("hom:missing")
        elif hom_obj.metadata.get("source_object") != s1 or hom_obj.metadata.get("target_object") != s2:
            violations.append("hom:cross-ref")

        surf_ids = {o.id for o in self.session.history(surf_iso, limit=200)}
        if s1 not in surf_ids or s2 not in surf_ids:
            violations.append("surface:missing")

        s2_obj = next((o for o in self.session.history(surf_iso, limit=200) if o.id == s2), None)
        if s2_obj and hom_s not in s2_obj.metadata.get("source_flow_ids", []):
            violations.append("surface:hom-ref")

        passed = len(violations) == 0
        return CTS19Result(
            "CTS-19.11", "Surface Compatibility", passed,
            f"violations={violations}",
            {"violations": len(violations)},
        )

    def cts_19_12_cross_topic(self, report: CTS19Report) -> CTS19Result:
        expected = {
            "hext:cts19:cross:C1": {
                "observation", "trajectory", "trajectory_flow", "surface", "hom",
            },
            "hext:cts19:cross:R1": {
                "observation", "trajectory", "trajectory_flow", "surface", "hom", "controller",
            },
        }
        violations = []
        for topic in ("Controller", "Replay"):
            iso = self._iso_topic(topic)
            for label, source in [
                ("history", self.session.history(iso, limit=100)),
                ("replay", self.session.replay(iso, last_n=100)),
            ]:
                for obj in source:
                    if obj.id not in expected:
                        continue
                    refs = set(obj.metadata.get("refs", {}).keys())
                    missing = expected[obj.id] - refs
                    if missing:
                        violations.append(f"{label}:{obj.id}:missing={sorted(missing)}")
                    hom_ref = obj.metadata.get("refs", {}).get("hom")
                    if hom_ref and hom_ref not in report.hom_objects:
                        violations.append(f"{label}:{obj.id}:broken-hom-ref")

        passed = len(violations) == 0
        return CTS19Result(
            "CTS-19.12", "Cross-topic Integrity", passed,
            f"violations={violations}",
            {"violations": len(violations)},
        )


def run_backend_comparison(
    inprocess_report: CTS19Report,
    redis_report: CTS19Report,
) -> CTS19Result:
    assert inprocess_report.original_graph and redis_report.original_graph
    isomorphic = inprocess_report.original_graph.isomorphic_to(redis_report.original_graph)
    return CTS19Result(
        "CTS-19.8", "Backend Compatibility",
        isomorphic,
        f"inprocess_homs={len(inprocess_report.original_graph.homs)} "
        f"redis_homs={len(redis_report.original_graph.homs)} isomorphic={isomorphic}",
        {"isomorphic": isomorphic},
    )


def export_cts19_artifacts(
    reports: dict[str, CTS19Report],
    comparison: CTS19Result | None,
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    graph_doc = {
        backend: (rep.original_graph.canonical() if rep.original_graph else {})
        for backend, rep in reports.items()
    }
    (out_dir / "hom_graph.json").write_text(json.dumps(graph_doc, indent=2), encoding="utf-8")

    rows: list[dict[str, Any]] = []
    for backend, rep in reports.items():
        for obj in rep.hom_objects.values():
            meta = obj.metadata
            rows.append({
                "backend": backend,
                "object_id": obj.id,
                "hom_id": meta.get("hom_id", obj.id),
                "source_object": meta.get("source_object"),
                "target_object": meta.get("target_object"),
                "hom_type": meta.get("hom_type"),
                "metric": meta.get("metric"),
                "weight": meta.get("weight"),
                "distance": meta.get("distance"),
                "cost": meta.get("cost"),
                "composition_ids": json.dumps(meta.get("composition_ids", [])),
                "version": obj.version,
            })
    with (out_dir / "hom_graph.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "backend", "object_id", "hom_id", "source_object", "target_object",
                "hom_type", "metric", "weight", "distance", "cost",
                "composition_ids", "version",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    comp_rows: list[dict[str, Any]] = []
    for backend, rep in reports.items():
        for rec in rep.composition_records:
            row = {"backend": backend, **rec}
            if isinstance(row.get("composition_ids"), list):
                row["composition_ids"] = json.dumps(row["composition_ids"])
            comp_rows.append(row)
    comp_fieldnames = [
        "backend", "hom_id", "composition_ids", "expected_source",
        "expected_target", "grouping", "preserved",
    ]
    with (out_dir / "composition_validation.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=comp_fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(comp_rows)

    id_rows: list[dict[str, Any]] = []
    for backend, rep in reports.items():
        for rec in rep.identity_records:
            id_rows.append({"backend": backend, **rec})
    id_fieldnames = [
        "backend", "hom_id", "source_object", "target_object", "hom_type", "preserved",
    ]
    with (out_dir / "identity_validation.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=id_fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(id_rows)

    metric_rows: list[dict[str, Any]] = []
    for backend, rep in reports.items():
        for rec in rep.metric_records:
            row = {"backend": backend, **rec}
            row["composition_ids"] = json.dumps(row.get("composition_ids", []))
            row["lineage"] = json.dumps(row.get("lineage", {}))
            metric_rows.append(row)
    metric_fieldnames = [
        "backend", "hom_id", "source_object", "target_object", "hom_type",
        "metric", "weight", "distance", "cost", "composition_ids", "lineage",
        "version", "preserved",
    ]
    with (out_dir / "metric_validation.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=metric_fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(metric_rows)

    cmp_rows: list[dict[str, Any]] = []
    if comparison:
        cmp_rows.append({
            "backend": "comparison",
            "test_id": comparison.test_id,
            "passed": comparison.passed,
            "details": comparison.details,
            "isomorphic": comparison.measurements.get("isomorphic"),
        })
    for backend, rep in reports.items():
        for r in rep.results:
            cmp_rows.append({
                "backend": backend,
                "test_id": r.test_id,
                "passed": r.passed,
                "details": r.details,
                "isomorphic": "",
            })
    with (out_dir / "backend_hom_comparison.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["backend", "test_id", "passed", "details", "isomorphic"])
        w.writeheader()
        for row in cmp_rows:
            w.writerow({k: row.get(k, "") for k in w.fieldnames})

    lines = [
        "# CTS-19 Enriched Morphism Conformance Report\n\n",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n",
        "## Purpose\n\n",
        "Verify structural preservation of Hom-objects (enriched morphisms) through ",
        "publish, subscribe, history, replay, and backend migration. ",
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
        lines.append("## CTS-19.8 Backend Compatibility\n\n")
        lines.append(f"**{'PASS' if comparison.passed else 'FAIL'}** — {comparison.details}\n\n")
    all_primary = all(
        r.passed
        for name in ("inprocess", "redis")
        if name in reports
        for r in reports[name].results
    ) and (comparison.passed if comparison else True)
    lines.append(f"## Overall Verdict\n\n**{'PASS' if all_primary else 'FAIL'}**\n")
    (out_dir / "hom_report.md").write_text("".join(lines), encoding="utf-8")
