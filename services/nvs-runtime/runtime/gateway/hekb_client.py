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
