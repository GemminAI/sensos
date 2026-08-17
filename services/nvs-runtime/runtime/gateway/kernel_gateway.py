"""Kernel gateway — all Kernel communication MUST go through this module.

EXP-Ubuntu011: transport now goes through the pooled, keep-alive async HTTP
client in runtime/gateway/http_pool.py (retry/backoff + connect/read
timeouts sourced from NetworkProfile) instead of opening a fresh
httpx.Client per call. The wire contract (POST /observe, GET /health,
Observation-ABI request/response shapes) is unchanged.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any

import httpx

from runtime.core.config import Settings, get_settings
from runtime.gateway.http_pool import RetryExhaustedError, request_with_retry
from runtime.models.enums import ForwardStatus, RuntimeEventType
from runtime.abi.observation import EventKind, ObservationEvent, ObserveRequest, ObserveResponse

logger = logging.getLogger(__name__)

#: The 38-Port SSOT (P01-P38, v1.4 Section 5.1) is a frozen, already-settled
#: fact, not a new decision made here — confirmed live across three prior
#: audit cycles (P02, P04, P17 all real, all returning 200). Validating
#: against it client-side, before any HTTP call, turns a caller's malformed
#: port_id into an immediate, clear local error instead of a confusing
#: remote 404 — it does not choose a port, a trigger, or any policy.
_PORT_ID_PATTERN = re.compile(r"^P(0[1-9]|[12][0-9]|3[0-8])$")

#: Runtime event types that get forwarded to the kernel as an Observation-ABI
#: event, and the EventKind they're recorded as. Every other RuntimeEventType
#: is a lifecycle/control-plane signal, not a Reality fact, and is skipped —
#: this preserves exactly what today's forwarding does, only fixing transport.
_FORWARDED_EVENT_KINDS: dict[RuntimeEventType, EventKind] = {
    RuntimeEventType.STATE_RAW: EventKind.OBSERVATION,
    RuntimeEventType.SEP_EXCITATION: EventKind.USER,
    RuntimeEventType.SEP_DISTURBANCE: EventKind.USER,
    RuntimeEventType.SEP_RAW: EventKind.USER,
}

#: Transport-level failures a caller should treat as "kernel unreachable
#: right now", not "this envelope is malformed".
_TRANSPORT_ERRORS = (httpx.HTTPError, RetryExhaustedError)


def _string_attributes(payload: dict[str, Any]) -> dict[str, str]:
    """Coerce an arbitrary runtime payload into the kernel's dict[str, str]
    attributes shape, losslessly (non-string values are JSON-encoded)."""
    result: dict[str, str] = {}
    for key, value in payload.items():
        result[str(key)] = value if isinstance(value, str) else json.dumps(value, default=str)
    return result


def _timestamp_ns(envelope: dict[str, Any]) -> int:
    raw = envelope.get("timestamp")
    if raw:
        try:
            return int(datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp() * 1e9)
        except ValueError:
            pass
    return time.time_ns()


def build_observation_event(envelope: dict[str, Any]) -> ObservationEvent | None:
    """Convert a runtime envelope into an Observation-ABI event, or None if
    this envelope's event_type isn't a Reality fact (session lifecycle,
    narrative, control, heartbeat, error) and should be skipped.

    Pulled out of forward_runtime_event() so ForwardWorker can build a batch
    of events across multiple queued envelopes without duplicating this
    mapping.
    """
    try:
        event_type = RuntimeEventType(envelope.get("event_type"))
    except ValueError:
        return None

    kind = _FORWARDED_EVENT_KINDS.get(event_type)
    if kind is None:
        return None

    payload = envelope.get("payload", {}) or {}
    return ObservationEvent(
        step=envelope.get("sequence_id", 0),
        timestamp_ns=_timestamp_ns(envelope),
        kind=kind,
        text=str(payload.get("text", "")),
        source=envelope.get("source_provider"),
        agent_id=envelope.get("agent_id"),
        attributes=_string_attributes(payload),
    )


class KernelGateway:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def base_url(self) -> str:
        return self.settings.nvs_kernel_url

    async def health_check(self) -> bool:
        try:
            response = await request_with_retry("GET", self.base_url, "/health")
            return response.status_code == 200
        except _TRANSPORT_ERRORS:
            return False

    async def observe(self, request: ObserveRequest) -> ObserveResponse:
        """Forward an Observation ABI request to nvs-kernel's real /observe.

        Pure transport: no vocabulary translation happens here. `request`
        must already be Observation-ABI-conformant before this is called.
        """
        response = await request_with_retry(
            "POST", self.base_url, "/observe", json=request.model_dump(mode="json")
        )
        response.raise_for_status()
        return ObserveResponse.model_validate(response.json())

    async def observe_batch(self, session_id: str, events: list[ObservationEvent]) -> ObserveResponse:
        """POST a single /observe request carrying multiple events.

        Batch Request (EXP-Ubuntu011 item 4): the kernel's ObserveRequest
        already accepts `events: list[ObservationEvent]` — batching here is
        purely a Runtime-side grouping change (fewer WAN round trips), the
        wire contract is unchanged.

        include_vectors=True (EXP-Ubuntu012B): Semantic Mapping needs the
        resulting geometry.position vector as CLE's lift input; without this
        flag nvs-kernel omits it (docs/OBSERVATION.md: "Vectors are opt-in").
        """
        return await self.observe(
            ObserveRequest(session_id=session_id, events=events, include_vectors=True)
        )

    async def invoke_port(self, port_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Invoke one of the 38 Core-wrapped Ports via nvs-kernel's real
        POST /ports/{port_id}_Port/invoke route.

        `port_id` is bare (e.g. "P04", "P17") — this method appends the
        `_Port` suffix, matching the addressing scheme already exercised
        against this live service (Projects/sensos/experiments/
        EXP-TRJ-38PORT-SEMANTIC-PERTURBATION-001/code/collector.py:
        `invoke_port(port_id, body) -> http("POST", f"/ports/{port_id}_Port/invoke", body)`,
        with previously captured evidence that all 38 Ports return 200
        under this exact URL shape).

        `body` is caller-assembled, not decided here: stateless Ports take
        their raw feature fields directly (e.g. P04: `{"vector": [...]}`);
        session-scoped Ports take `{"session_id": ..., **extra}`. This
        mirrors CLEClient.call()'s existing "no route-specific method
        commits to a payload shape" pattern, for the same reason — the 38
        Ports' request/response schemas vary per port and no single ABI
        type covers them.

        Pure transport, read-only: the 38 Ports are confirmed
        observation-only (no intervention fields found in any real
        captured response body across a prior live pilot run), so this
        method performs no local mutation and expects none server-side.

        Raises ValueError before any HTTP call if `port_id` is not a real
        P01-P38 identifier (the frozen 38-Port SSOT) — a client-side check
        against an already-settled fact, not a new port/trigger decision.
        """
        if not _PORT_ID_PATTERN.match(port_id):
            raise ValueError(
                f"port_id {port_id!r} is not a valid Port identifier; must be "
                "P01-P38 per the v1.4 Section 5.1 38-Port SSOT"
            )
        response = await request_with_retry(
            "POST", self.base_url, f"/ports/{port_id}_Port/invoke", json=body
        )
        response.raise_for_status()
        return response.json()

    async def get_port_capability(self, port_id: str) -> dict[str, Any]:
        """Real, live GET /ports/{port_id}_Port capability descriptor —
        nvs-kernel's own existing schema, not invented here: `{type, id,
        layer, name, version, status, input: {type, schema_uri},
        output: {type, schema_uri}, capabilities, provider:
        {implementation, abi_version}, invoke_endpoints}`. Confirmed live
        for both the 8 L0-L7 layer Ports (via GET /ports) and the 38
        individually-addressed P0x Ports (e.g. live P04_Port:
        status="IMPLEMENTED", capabilities=["core_c04_hext_closure_verifier"]).

        This is the read-only "is this capability available?" boundary —
        no invocation happens here, matching `invoke_port()`'s own
        read-only-observation guarantee for the same 38-Port SSOT.

        Raises ValueError before any HTTP call for the same reason
        `invoke_port()` does.
        """
        if not _PORT_ID_PATTERN.match(port_id):
            raise ValueError(
                f"port_id {port_id!r} is not a valid Port identifier; must be "
                "P01-P38 per the v1.4 Section 5.1 38-Port SSOT"
            )
        response = await request_with_retry("GET", self.base_url, f"/ports/{port_id}_Port")
        response.raise_for_status()
        return response.json()

    async def forward_runtime_event(self, envelope: dict[str, Any]) -> tuple[ForwardStatus, str | None]:
        """Forward a single runtime envelope to the kernel via the real
        /observe contract. Batch-of-one convenience wrapper around
        observe_batch(); ForwardWorker uses build_observation_event() +
        observe_batch() directly to batch multiple envelopes together.
        """
        observation_event = build_observation_event(envelope)
        if observation_event is None:
            return ForwardStatus.SKIPPED, None

        try:
            response = await self.observe_batch(str(envelope.get("session_id")), [observation_event])
        except _TRANSPORT_ERRORS as exc:
            logger.warning("Kernel unavailable: %s", exc)
            return ForwardStatus.PENDING, None
        # TODO(RFC-SensOS21-Follow-up): ObserveResponse.control (tier/intervention)
        # is discarded here. RFC-SensOS21/22/23 define a Governance -> Goal ->
        # Directive -> Instruction chain; this is the likely future bridge from
        # Kernel Executive into that chain. Not wired up in this change.
        return ForwardStatus.FORWARDED, str(response.cycle)
