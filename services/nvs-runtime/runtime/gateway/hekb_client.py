"""HEKB client.

EXP-Ubuntu011 gave this client pooled/async/retry/timeout transport, same as
NVS and CLE. EXP-Ubuntu012B adds `store()`, the CLE-output -> HEKB-object
mapping (Semantic Mapping, the "Memory Adapter" leg): `build_hekb_object()`
maps a CLE `LiftResponse` body onto the existing HEKB API's `POST /v1/objects`
request shape (`hekb.api.ObjectCreateRequest`: kind/created_ns/vector/
attributes/labels — see EXP-Ubuntu012A, `GemminAI/hekb/python/hekb/api.py`),
and `store()` posts it. No new HEKB schema, endpoint, or embedding — this is
a field-rename/type-coercion mapping onto a request shape that already exists
end to end.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from runtime.core.config import Settings, get_settings
from runtime.gateway.http_pool import RetryExhaustedError, request_with_retry

_TRANSPORT_ERRORS = (RetryExhaustedError,)


def build_hekb_object(
    lift_result: dict[str, Any], *, position: list[float], session_id: str, cycle: int
) -> dict[str, Any]:
    """CLE `LiftResponse` (dict, as returned by `CLEClient.lift`) -> the
    existing HEKB `POST /v1/objects` request shape.

    Every field below already exists on one side or the other; this is a
    rename/cast, not new semantics:

    - `kind`: HEKB's existing `HextKind.OBSERVATION` — this object records
      one Observation's lifted result, and no other existing `HextKind`
      value fits better.
    - `vector`: the same position vector CLE was given as its lift input
      (`states[0].theta` is not echoed back in `LiftResponse`, so the
      caller threads it through — see
      `ForwardWorker._propagate_semantic_mapping`).
    - `attributes`: the float-valued fields CLE's `LiftResponse` already
      carries (`compression_ratio`, the three Betti numbers, the Euler
      characteristic), coerced to `dict[str, float]` per HEKB's existing
      schema.
    - `labels`: the string-valued identifiers already on `LiftResponse`
      (`concept_id`, `normalized_hash`) plus the NVS coordinates
      (`session_id`, `cycle`) that produced them, coerced to
      `dict[str, str]` per HEKB's existing schema.
    """
    invariants = lift_result.get("invariants", {}) or {}
    proof = lift_result.get("proof", {}) or {}
    attributes: dict[str, float] = {
        "betti_0": float(invariants.get("betti_0", 0)),
        "betti_1": float(invariants.get("betti_1", 0)),
        "betti_2": float(invariants.get("betti_2", 0)),
        "euler_characteristic": float(invariants.get("euler_characteristic", 0)),
        "compression_ratio": float(lift_result.get("compression_ratio", 0.0)),
    }
    labels: dict[str, str] = {
        "concept_id": str(lift_result.get("concept_id", "")),
        "normalized_hash": str(lift_result.get("normalized_hash", "")),
        "session_id": session_id,
        "cycle": str(cycle),
        "proof_is_valid": str(bool(proof.get("is_valid", False))),
    }
    return {
        "kind": "OBSERVATION",
        "vector": list(position),
        "attributes": attributes,
        "labels": labels,
    }


def build_hekb_object_from_port_result(
    port_id: str,
    port_result: dict[str, Any],
    *,
    session_id: str | None = None,
    cycle: int | None = None,
    runtime_cycle_id: str | None = None,
) -> dict[str, Any]:
    """One real 38-Port invoke result -> the existing HEKB `POST /v1/objects`
    request shape.

    Unlike `build_hekb_object()` (CLE `LiftResponse` -> HEKB), the 38 Ports'
    response schemas vary per port (P04 returns a scalar `residual`/`closed`
    pair, P02 returns `betti`/`identity_code`, etc. -- confirmed by live
    invocation) and no single ABI type covers them, so this does not attempt
    to interpret or flatten `port_result` into `vector`/`attributes`
    (float-typed fields) -- doing so would mean guessing a per-port
    numeric-extraction rule this repo has no evidence for. Instead the raw
    result is preserved verbatim, JSON-encoded into `labels` (already
    string-typed per HEKB's existing schema) -- the same
    encode-non-string-values-losslessly technique
    `kernel_gateway._string_attributes()` already uses elsewhere in this
    codebase, not a new one invented here.

    - `kind`: HEKB's existing `HextKind.EVIDENCE` (`GemminAI/hekb/python/
      hekb/model.py`) -- a real, pre-existing member of HEKB's closed object
      vocabulary, distinct from the `OBSERVATION` kind `build_hekb_object()`
      already uses for CLE lift results, and a better semantic fit for a
      Port's read-only observation result.
    - `vector` / `attributes`: left empty (schema defaults) -- not fabricated
      from `port_result`, for the reason above.
    - `labels`: `port_id` and `session_id` (when present) preserved exactly;
      `raw_result` carries the complete, unmodified Port response;
      `value_kind: "measured"` marks this as raw measured data, not
      anything derived (no Var[S]/H_comp/Triad computation happens here,
      and none is claimed) -- this is a Port Evidence record, not a v1.4
      Canonical Observation, which requires EOU data this repo does not
      have (see Reality Audit).

    `runtime_cycle_id` (when present) is the Runtime Decision Boundary's
    own cycle identity (an Event.event_id — see
    `runtime.services.capability_decision`), kept deliberately separate
    from `cycle` (NVS-Kernel's own integer `/observe` cycle counter,
    `ObserveResponse.cycle`) — the two are different identities from
    different systems, and conflating them under one label would be a
    fabricated equivalence this repo has no evidence for.
    """
    labels: dict[str, str] = {
        "port_id": port_id,
        "value_kind": "measured",
        "raw_result": json.dumps(port_result, default=str),
    }
    if session_id is not None:
        labels["session_id"] = session_id
    if cycle is not None:
        labels["cycle"] = str(cycle)
    if runtime_cycle_id is not None:
        labels["runtime_cycle_id"] = runtime_cycle_id

    return {
        "kind": "EVIDENCE",
        "vector": [],
        "attributes": {},
        "labels": labels,
    }


def build_hekb_object_from_trajectory(
    trajectory: Any,
    *,
    session_id: str | None = None,
    runtime_cycle_id: str | None = None,
) -> dict[str, Any]:
    """One real `msr.abi.StabilizedTrajectory` (meaning-space-runtime) -> the
    existing HEKB `POST /v1/objects` request shape.

    Unlike `build_hekb_object_from_port_result()`, a StabilizedTrajectory's
    numeric fields ARE a known, consistent shape (a single geometric
    position with a covariance) -- the same character as
    `build_hekb_object()`'s own CLE-lift `position`, not the
    heterogeneous-per-port character `build_hekb_object_from_port_result()`
    guards against. So `centroid` goes into the real `vector` field and the
    scalar dwell fields go into real `attributes`, matching the existing
    `build_hekb_object()` precedent for genuine geometric measurements.
    `covariance` (a matrix) and `provenance` (a tuple of strings) have no
    home in HEKB's flat float/string schema, so they are JSON-encoded into
    `labels`, the same lossless-encoding technique already used elsewhere
    in this module.

    `trajectory` is duck-typed (not imported as `msr.abi.StabilizedTrajectory`
    to avoid this gateway module depending on the `msr` package) -- it must
    have `.trajectory_id`, `.frame_id`, `.basin_id`, `.centroid`,
    `.covariance`, `.dwell_steps`, `.dwell_seconds`, `.is_novel`,
    `.provenance`, `.dimension`.
    """
    labels: dict[str, str] = {
        "trajectory_id": trajectory.trajectory_id,
        "frame_id": trajectory.frame_id,
        "basin_id": trajectory.basin_id if trajectory.basin_id is not None else "",
        "is_novel": str(trajectory.is_novel),
        "value_kind": "measured",
        "covariance": json.dumps([list(row) for row in trajectory.covariance]),
        "provenance": json.dumps(list(trajectory.provenance)),
    }
    if session_id is not None:
        labels["session_id"] = session_id
    if runtime_cycle_id is not None:
        labels["runtime_cycle_id"] = runtime_cycle_id

    return {
        "kind": "EVIDENCE",
        "vector": list(trajectory.centroid),
        "attributes": {
            "dwell_steps": float(trajectory.dwell_steps),
            "dwell_seconds": float(trajectory.dwell_seconds),
            "dimension": float(trajectory.dimension),
        },
        "labels": labels,
    }


def build_hekb_object_from_triangulation(
    triangulation: Any,
    *,
    session_id: str | None = None,
    runtime_cycle_id: str | None = None,
) -> dict[str, Any]:
    """One real `runtime.services.meaning_triangulation.TriangulationResult`
    -> the existing HEKB `POST /v1/objects` request shape.

    `triangulation` is duck-typed (not imported from
    `runtime.services.meaning_triangulation`, for the same reason
    `build_hekb_object_from_trajectory()` duck-types its own argument: this
    gateway module does not depend on the service layer that calls it) --
    it must have `.triangulation_id`, `.state`, `.divergence_epsilon`,
    `.note`, `.measurements` (each with `.path_id`, `.method`,
    `.observation_ids`, `.stabilized`, and — when stabilized — a
    `.run_result.trajectory` with `.trajectory_id`), and `.pairwise` (each
    with `.path_a`, `.path_b`, `.both_stabilized`, `.centroid_distance`,
    `.same_basin`, `.basin_signal_meaningful`).

    This object is the triangulation SUMMARY, not a substitute for the
    underlying per-path evidence: it carries no `vector` of its own (a
    triangulation result has no single geometric position — the geometry
    lives on each path's own `StabilizedTrajectory`, which
    `request_meaning_triangulation()` persists separately via the existing
    `build_hekb_object_from_trajectory()`, one real HEKB write per
    stabilized path). `value_kind: "derived"` marks this object as an
    aggregate over those measurements, distinct from
    `build_hekb_object_from_trajectory()`'s `value_kind: "measured"` for
    the measurements themselves -- the same label, a different value, so a
    reader never has to guess which kind of evidence they are looking at.
    Every path's raw observation ids, method label, and (for stabilized
    paths) trajectory id are preserved verbatim in `labels`, JSON-encoded
    the same lossless way the rest of this module already does for
    non-scalar data -- `request_meaning_triangulation()` additionally
    creates a real HEKB morphism (`DERIVES`) from each per-path trajectory
    object to this summary object, so the lineage is a real graph edge, not
    only a label.
    """
    path_summaries = [
        {
            "path_id": measurement.path_id,
            "method": measurement.method,
            "observation_ids": list(measurement.observation_ids),
            "stabilized": measurement.stabilized,
            "trajectory_id": (
                measurement.run_result.trajectory.trajectory_id if measurement.stabilized else None
            ),
        }
        for measurement in triangulation.measurements
    ]
    pairwise_summaries = [
        {
            "path_a": pair.path_a,
            "path_b": pair.path_b,
            "both_stabilized": pair.both_stabilized,
            "centroid_distance": pair.centroid_distance,
            "same_basin": pair.same_basin,
            "basin_signal_meaningful": pair.basin_signal_meaningful,
        }
        for pair in triangulation.pairwise
    ]
    centroid_distances = [p.centroid_distance for p in triangulation.pairwise if p.centroid_distance is not None]

    attributes: dict[str, float] = {
        "path_count": float(len(triangulation.measurements)),
        "stabilized_count": float(sum(1 for m in triangulation.measurements if m.stabilized)),
    }
    if triangulation.divergence_epsilon is not None:
        attributes["divergence_epsilon"] = float(triangulation.divergence_epsilon)
    if centroid_distances:
        attributes["max_centroid_distance"] = float(max(centroid_distances))
        attributes["min_centroid_distance"] = float(min(centroid_distances))

    labels: dict[str, str] = {
        "triangulation_id": triangulation.triangulation_id,
        "state": triangulation.state.value,
        "note": triangulation.note,
        "value_kind": "derived",
        "paths": json.dumps(path_summaries),
        "pairwise": json.dumps(pairwise_summaries),
    }
    if session_id is not None:
        labels["session_id"] = session_id
    if runtime_cycle_id is not None:
        labels["runtime_cycle_id"] = runtime_cycle_id

    return {"kind": "EVIDENCE", "vector": [], "attributes": attributes, "labels": labels}


class HekbClient:
    """One client, one backend: hekbd (ADR-0013). Every method below talks
    to `self.base_url`; there is no second URL to route around."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def base_url(self) -> str:
        return self.settings.hekb_url

    async def health_check(self) -> bool:
        try:
            response = await request_with_retry("GET", self.base_url, "/health")
            return response.status_code == 200
        except _TRANSPORT_ERRORS:
            return False

    async def call(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        """Generic pooled/retried call against any hekbd route. Returns the
        parsed JSON body."""
        response = await request_with_retry(method, self.base_url, path, json=json)
        response.raise_for_status()
        return response.json()

    async def store(self, knowledge_object: dict[str, Any]) -> dict[str, Any]:
        """Persist one object via hekbd's `POST /v1/objects`.

        `knowledge_object` is expected to already be shaped like
        `build_hekb_object()`'s output. hekbd's own response is `{"id"}`;
        normalized here to `{"object_id": id, "hash": id}` (content
        addressing means the id *is* the hash — the same convention
        `hekb-api`'s own `ObjectCreateResponse` already used,
        `hash == object_id` in every example observed) so every existing
        caller (`stored.get("object_id")`) is unaffected by ADR-0013's
        backend switch.
        """
        result = await self.call("POST", "/v1/objects", json=knowledge_object)
        return {"object_id": result["id"], "hash": result["id"]}

    # -- Read MCP: wraps hekbd's existing object/morphism/query routes ----
    # (`GemminAI/hekb` docs/API.md / cpp/server/http_api.cpp), the same
    # contract `hekb/python/hekb/client.py`'s HekbClient wraps. No new HEKB
    # route or payload shape is invented here — every path/body/response
    # key below matches that server's own routes exactly, confirmed by
    # reading its route table before writing this.

    async def get_object(self, object_id: str) -> dict[str, Any] | None:
        """GET /v1/objects/{id}. Read-only. Returns None on 404 (an object
        genuinely not existing is a normal outcome, not a failure) —
        mirrors `hekb.client.HekbClient.get()`'s own None-on-404 contract."""
        response = await request_with_retry("GET", self.base_url, f"/v1/objects/{object_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def nearest(
        self, vector: list[float], limit: int = 10, metric: str = "cosine"
    ) -> list[dict[str, Any]]:
        """POST /v1/query/nearest. Read-only (query.py's `nearest()` on the
        server does not mutate the store — see GemminAI/hekb's own
        docstring: "Exact k-nearest search"). Returns the `matches` list
        verbatim (`[{"id", "distance"}, ...]`)."""
        result = await self.call(
            "POST", "/v1/query/nearest", json={"vector": vector, "limit": limit, "metric": metric}
        )
        return list(result.get("matches", []))

    async def neighbours(self, object_id: str, depth: int = 1) -> list[dict[str, Any]]:
        """GET /v1/query/neighbours?id=&depth=. Read-only BFS expansion.
        Returns the `neighbours` list verbatim (`[{"id","via","hops"}, ...]`)."""
        query = urlencode({"id": object_id, "depth": depth})
        result = await self.call("GET", f"/v1/query/neighbours?{query}")
        return list(result.get("neighbours", []))

    async def geodesic(self, source: str, target: str) -> dict[str, Any]:
        """GET /v1/query/geodesic?from=&to=. Read-only shortest path.
        Returns `{"found","cost","objects","morphisms"}` verbatim —
        `found: false` (no path) is a real, non-error outcome, not raised."""
        query = urlencode({"from": source, "to": target})
        return await self.call("GET", f"/v1/query/geodesic?{query}")

    async def stats(self) -> dict[str, int]:
        """GET /metrics (Prometheus text) on hekbd, parsed the same way
        `hekb.client.HekbClient.stats()` parses it — no new parsing rule
        invented, same two counter lines (`hekb_objects`, `hekb_morphisms`)."""
        response = await request_with_retry("GET", self.base_url, "/metrics")
        response.raise_for_status()
        counts: dict[str, int] = {}
        for line in response.text.splitlines():
            if line.startswith("hekb_objects "):
                counts["objects"] = int(float(line.split()[1]))
            elif line.startswith("hekb_morphisms "):
                counts["morphisms"] = int(float(line.split()[1]))
        return counts

    async def relate(self, source: str, target: str, kind: str, weight: float = 0.0) -> str:
        """POST /v1/morphisms. NOT a read — this WRITES a morphism (edge)
        into hekbd's graph. Kept as its own method (not folded into
        `store()`) because its response shape (`{"id"}`) and payload
        (source/target/kind/weight) are morphism-specific, not object
        create/read."""
        result = await self.call(
            "POST",
            "/v1/morphisms",
            json={"source": source, "target": target, "kind": kind, "weight": weight},
        )
        return str(result["id"])
