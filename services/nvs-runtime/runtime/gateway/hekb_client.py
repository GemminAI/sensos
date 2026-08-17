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


class HekbClient:
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

    async def call(self, method: str, path: str, *, json: dict[str, Any] | None = None):
        """Generic pooled/retried call against any HEKB route. Returns the
        parsed JSON body. This is the only way this client talks to HEKB
        today — no route-specific method commits to a payload shape."""
        response = await request_with_retry(method, self.base_url, path, json=json)
        response.raise_for_status()
        return response.json()

    async def store(self, knowledge_object: dict[str, Any]) -> dict[str, Any]:
        """Persist one object via HEKB's existing POST /v1/objects.

        `knowledge_object` is expected to already be shaped like
        `build_hekb_object()`'s output. Returns HEKB's existing
        `{object_id, hash, timestamp}` response verbatim.
        """
        return await self.call("POST", "/v1/objects", json=knowledge_object)
