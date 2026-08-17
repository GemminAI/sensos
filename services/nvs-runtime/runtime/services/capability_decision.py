"""Runtime Decision Boundary — the smallest deterministic substrate
connecting: Runtime Cycle -> Capability Request -> Capability Discovery ->
Decision -> MCP/Gateway invocation -> Result -> Evidence -> Lineage.

This is NOT a CPS service, planner, or semantic router. Given a
CapabilityRequest, `request_capability()` asks ONE deterministic question —
"is this capability available, and if so, was invoking it successful?" —
using only real, already-verified mechanisms:

- Capability identity/validation: `KernelGateway`'s existing 38-Port SSOT
  check (this module does not duplicate it).
- Capability discovery: `KernelGateway.get_port_capability()` — real, live
  `GET /ports/{id}_Port` descriptor, not fabricated here.
- Invocation: `KernelGateway.invoke_port()` — the existing, already-verified
  real Port invoke contract.
- Evidence: `build_hekb_object_from_port_result()` + `HekbClient.store()` —
  the existing Port-Evidence-to-HEKB pipeline (same logic as
  `ForwardWorker.persist_port_evidence()`).
- Lineage: `EventService.ingest()` — the existing Event/Redis/DB mechanism.
  No parallel lineage system is created. Two new, additive
  `RuntimeEventType` values (`CAPABILITY_REQUESTED`, `CAPABILITY_RESULT`)
  record the request and its outcome as a `parent_event_id`-linked pair;
  neither is added to `kernel_gateway._FORWARDED_EVENT_KINDS`, so
  ForwardWorker correctly SKIPs re-forwarding them to NVS `/observe` (they
  are not Reality-fact observations — they are records of calls this
  module already made directly to NVS's Port routes).

The Runtime Cycle's identity (`runtime_cycle_id`) IS the CAPABILITY_REQUESTED
event's `event_id` — no separate Cycle table was added, per the Reality
Audit's finding that the existing Event/Experiment schema already covers
this without a new model.

No capability_id is ever hard-coded here. The caller supplies it; this
module treats it as an opaque string, valid or not, available or not —
never a semantic routing decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from runtime.gateway.hekb_client import HekbClient, build_hekb_object_from_port_result
from runtime.gateway.http_pool import RetryExhaustedError
from runtime.gateway.kernel_gateway import KernelGateway
from runtime.models.enums import RuntimeEventType
from runtime.models.schemas import EventIngestRequest
from runtime.services.event_service import EventService

_TRANSPORT_ERRORS = (httpx.HTTPError, RetryExhaustedError)


class RuntimeOutcome(StrEnum):
    """The Runtime Decision Boundary's own outcome vocabulary — distinct
    from ForwardStatus, DAKDecision-style enums, or ObservationState: none
    of those answer this boundary's specific question, "was this capability
    request permitted and executed?" """

    INVALID = "INVALID"  # capability_id failed KernelGateway's own SSOT/format check
    UNAVAILABLE = "UNAVAILABLE"  # capability descriptor's status != IMPLEMENTED
    BLOCKED = "BLOCKED"  # capability discovery itself failed (external infra unreachable)
    INVOCATION_FAILED = "INVOCATION_FAILED"  # discovery said available, but invoke failed
    SUCCESS = "SUCCESS"  # invoked successfully (evidence persistence tracked separately)


class EvidenceStatus(StrEnum):
    PERSISTED = "PERSISTED"
    BLOCKED = "BLOCKED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


@dataclass(frozen=True)
class CapabilityRequest:
    """"Runtime requests capability X for cycle Y." `capability_id` is
    opaque to this module (currently always a Port SSOT id, e.g. "P04" —
    validated by KernelGateway itself, not re-validated/duplicated here).
    No semantic Port selection is expressed or implied by this type."""

    capability_id: str
    input: dict[str, Any]
    reason: str | None = None


@dataclass(frozen=True)
class CapabilityResult:
    runtime_cycle_id: UUID
    outcome: RuntimeOutcome
    capability_descriptor: dict[str, Any] | None = None
    invocation_result: dict[str, Any] | None = None
    evidence_status: EvidenceStatus = EvidenceStatus.NOT_ATTEMPTED
    evidence_object_id: str | None = None
    result_event_id: UUID | None = None


async def request_capability(
    db: Session,
    session_id: UUID,
    agent_id: UUID,
    request: CapabilityRequest,
    *,
    gateway: KernelGateway | None = None,
    hekb: HekbClient | None = None,
    event_service: EventService | None = None,
) -> CapabilityResult:
    """The Runtime Decision Boundary. `session_id`/`agent_id` must already
    be registered (same requirement as the existing `nvs_emit_sep_event`
    MCP tool) — this module does not invent a "system agent" identity.

    Never silently converts a failure to success: INVALID / UNAVAILABLE /
    BLOCKED / INVOCATION_FAILED / SUCCESS are mutually exclusive and always
    determined from a real check or a real call's real outcome.
    """
    gateway = gateway or KernelGateway()
    hekb = hekb or HekbClient()
    event_service = event_service or EventService()

    request_ingest = event_service.ingest(
        db,
        session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.CAPABILITY_REQUESTED,
            agent_id=agent_id,
            payload={
                "capability_id": request.capability_id,
                "input": request.input,
                "reason": request.reason,
            },
        ),
    )
    runtime_cycle_id = request_ingest.event_ids[0]

    capability_descriptor: dict[str, Any] | None = None
    invocation_result: dict[str, Any] | None = None
    evidence_status = EvidenceStatus.NOT_ATTEMPTED
    evidence_object_id: str | None = None

    try:
        capability_descriptor = await gateway.get_port_capability(request.capability_id)
    except ValueError:
        outcome = RuntimeOutcome.INVALID
    except _TRANSPORT_ERRORS:
        outcome = RuntimeOutcome.BLOCKED
    else:
        if capability_descriptor.get("status") != "IMPLEMENTED":
            outcome = RuntimeOutcome.UNAVAILABLE
        else:
            try:
                invocation_result = await gateway.invoke_port(request.capability_id, request.input)
            except _TRANSPORT_ERRORS:
                outcome = RuntimeOutcome.INVOCATION_FAILED
            else:
                outcome = RuntimeOutcome.SUCCESS
                try:
                    hekb_object = build_hekb_object_from_port_result(
                        request.capability_id,
                        invocation_result,
                        session_id=str(session_id),
                        runtime_cycle_id=str(runtime_cycle_id),
                    )
                    stored = await hekb.store(hekb_object)
                    evidence_status = EvidenceStatus.PERSISTED
                    evidence_object_id = stored.get("object_id")
                except _TRANSPORT_ERRORS:
                    evidence_status = EvidenceStatus.BLOCKED

    result_ingest = event_service.ingest(
        db,
        session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.CAPABILITY_RESULT,
            agent_id=agent_id,
            parent_event_id=runtime_cycle_id,
            payload={
                "outcome": outcome.value,
                "capability_descriptor": capability_descriptor,
                "invocation_result": invocation_result,
                "evidence_status": evidence_status.value,
                "evidence_object_id": evidence_object_id,
            },
        ),
    )

    return CapabilityResult(
        runtime_cycle_id=runtime_cycle_id,
        outcome=outcome,
        capability_descriptor=capability_descriptor,
        invocation_result=invocation_result,
        evidence_status=evidence_status,
        evidence_object_id=evidence_object_id,
        result_event_id=result_ingest.event_ids[0],
    )
