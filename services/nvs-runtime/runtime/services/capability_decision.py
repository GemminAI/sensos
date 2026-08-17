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

A second capability kind, `request_meaning_trajectory()`, was added
alongside `request_capability()` for the MeaningMapper -> meaning-space-
runtime -> Trajectory chain. It reuses the same RuntimeOutcome/
EvidenceStatus vocabulary and the same Event/HEKB lineage mechanisms, but
is a separate function rather than a generalization of
`request_capability()`, because its invocation is an in-process Python
call, not an HTTP request through `KernelGateway` — see that function's
own docstring for the SPEC_DECISION_REQUIRED note on whether a shared
"CapabilityProvider" abstraction should unify the two later.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from msr.errors import MSRError

from runtime.gateway.hekb_client import (
    HekbClient,
    build_hekb_object_from_port_result,
    build_hekb_object_from_trajectory,
    build_hekb_object_from_triangulation,
)
from runtime.gateway.http_pool import RetryExhaustedError
from runtime.gateway.kernel_gateway import KernelGateway
from runtime.models.enums import RuntimeEventType
from runtime.models.schemas import EventIngestRequest
from runtime.services.event_service import EventService
from runtime.services.meaning_trajectory import run_meaning_trajectory
from runtime.services.meaning_triangulation import TriangulationInput, run_meaning_triangulation

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


async def request_meaning_trajectory(
    db: Session,
    session_id: UUID,
    agent_id: UUID,
    observations: list[dict[str, Any]],
    *,
    capability_id: str = "meaning_mapper.trajectory",
    hekb: HekbClient | None = None,
    event_service: EventService | None = None,
) -> CapabilityResult:
    """The Runtime Decision Boundary for the MeaningMapper capability:
    MeaningMapper -> meaning-space-runtime -> Trajectory (see
    `runtime.services.meaning_trajectory.run_meaning_trajectory()`).

    Structurally parallel to `request_capability()` — same
    CapabilityRequest-shaped lineage, same RuntimeOutcome/EvidenceStatus
    vocabulary, same Event/HEKB mechanisms — but a separate function, not
    a shared one, because this capability's invocation is a direct
    in-process Python call with no HTTP, no `KernelGateway`, and no live
    `GET .../capability` descriptor to check — a genuinely different
    transport from Port invocation, not merely a style choice.

    SPEC_DECISION_REQUIRED (flagged, not decided): whether
    `request_capability()` and this function should later be unified
    behind one pluggable "CapabilityProvider" interface (discovery +
    invoke), now that two real, structurally-parallel-but-not-shared
    implementations exist. No such interface exists anywhere in this
    repository today, and inventing one now would be exactly the kind of
    speculative abstraction this cycle's instructions prohibit.

    `capability_descriptor` here is always a static dict — this capability
    is a local library import, not a live external service reachability
    question, so there is no real "is it up right now" check to perform
    (an honest, non-fabricated distinction from Port's live discovery, not
    glossed over).
    """
    hekb = hekb or HekbClient()
    event_service = event_service or EventService()

    request_ingest = event_service.ingest(
        db,
        session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.CAPABILITY_REQUESTED,
            agent_id=agent_id,
            payload={
                "capability_id": capability_id,
                "input": {"observation_count": len(observations)},
                "reason": None,
            },
        ),
    )
    runtime_cycle_id = request_ingest.event_ids[0]

    capability_descriptor: dict[str, Any] = {
        "capability_id": capability_id,
        "status": "IMPLEMENTED",
        "transport": "in-process",
    }
    invocation_result: dict[str, Any] | None = None
    evidence_status = EvidenceStatus.NOT_ATTEMPTED
    evidence_object_id: str | None = None

    if not observations:
        outcome = RuntimeOutcome.INVALID
    else:
        try:
            run_result = run_meaning_trajectory(observations)
        except MSRError:
            outcome = RuntimeOutcome.INVOCATION_FAILED
        else:
            outcome = RuntimeOutcome.SUCCESS
            invocation_result = {
                "steps_processed": len(run_result.steps),
                "quarantined_count": sum(1 for s in run_result.steps if s.quarantined),
                "stabilized": run_result.stabilized,
                "trajectory_id": (
                    run_result.trajectory.trajectory_id if run_result.trajectory else None
                ),
            }
            if run_result.trajectory is not None:
                try:
                    hekb_object = build_hekb_object_from_trajectory(
                        run_result.trajectory,
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


async def request_meaning_triangulation(
    db: Session,
    session_id: UUID,
    agent_id: UUID,
    inputs: list[TriangulationInput],
    *,
    divergence_epsilon: float | None = None,
    capability_id: str = "meaning_mapper.triangulation",
    hekb: HekbClient | None = None,
    event_service: EventService | None = None,
) -> CapabilityResult:
    """The Runtime Decision Boundary for Meaning Triangulation: runs
    `runtime.services.meaning_triangulation.run_meaning_triangulation()`
    (itself built on the real MeaningMapper -> MSR chain), then persists
    the result to HEKB as real, linked evidence — never as a substitute
    for the underlying observations.

    Structurally parallel to `request_meaning_trajectory()` (same
    RuntimeOutcome/EvidenceStatus vocabulary, same Event/HEKB lineage
    mechanism, same in-process/no-live-descriptor character), extended one
    step further because triangulation evidence is not one HEKB object but
    a small, real graph: one EVIDENCE object per stabilized path's
    `StabilizedTrajectory` (via the existing `build_hekb_object_from_
    trajectory()`), one EVIDENCE object for the triangulation summary
    itself (via the new `build_hekb_object_from_triangulation()`), and a
    real `DERIVES` morphism from each path's trajectory object to the
    summary object (via `HekbClient.relate()` — the Phase 1 HEKB Read/Write
    MCP client method) so the summary's lineage back to its raw evidence is
    a graph edge, not only a JSON blob inside the summary's own labels.

    `evidence_status` is `PERSISTED` only if every one of those writes
    (trajectories, summary, and every `relate()` edge) succeeds; any
    transport failure at any step reports `BLOCKED` — a partially-written
    graph (e.g. the summary object exists but a DERIVES edge does not) is
    never reported as success.
    """
    hekb = hekb or HekbClient()
    event_service = event_service or EventService()

    request_ingest = event_service.ingest(
        db,
        session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.CAPABILITY_REQUESTED,
            agent_id=agent_id,
            payload={
                "capability_id": capability_id,
                "input": {"path_count": len(inputs), "divergence_epsilon": divergence_epsilon},
                "reason": None,
            },
        ),
    )
    runtime_cycle_id = request_ingest.event_ids[0]

    capability_descriptor: dict[str, Any] = {
        "capability_id": capability_id,
        "status": "IMPLEMENTED",
        "transport": "in-process",
    }
    invocation_result: dict[str, Any] | None = None
    evidence_status = EvidenceStatus.NOT_ATTEMPTED
    evidence_object_id: str | None = None

    if not inputs:
        outcome = RuntimeOutcome.INVALID
    else:
        triangulation = run_meaning_triangulation(
            inputs, triangulation_id=str(runtime_cycle_id), divergence_epsilon=divergence_epsilon
        )
        outcome = RuntimeOutcome.SUCCESS
        invocation_result = {
            "triangulation_id": triangulation.triangulation_id,
            "state": triangulation.state.value,
            "note": triangulation.note,
            "path_count": len(triangulation.measurements),
            "stabilized_count": sum(1 for m in triangulation.measurements if m.stabilized),
            "pairwise": [
                {
                    "path_a": p.path_a,
                    "path_b": p.path_b,
                    "both_stabilized": p.both_stabilized,
                    "centroid_distance": p.centroid_distance,
                    "same_basin": p.same_basin,
                    "basin_signal_meaningful": p.basin_signal_meaningful,
                }
                for p in triangulation.pairwise
            ],
        }

        try:
            # Writes go through `call_query()` (hekbd, `hekb_query_url`),
            # not `store()` (hekb-api, `hekb_url`) — discovered live (not
            # assumed) while wiring this end to end: `relate()`/
            # `neighbours()`/`get_object()` only exist on hekbd, and hekbd
            # is its own separate datastore from hekb-api (confirmed by
            # reading both servers — see docs/audit/HEKB_HEXT_
            # INVESTIGATION_20260817.md). An id hekb-api issued would not
            # exist in hekbd's graph, so `relate()` on it would fail every
            # time, not just under test. `request_capability()` and
            # `request_meaning_trajectory()` above are unchanged and still
            # use `store()` — this is a deliberate, scoped choice for
            # triangulation evidence specifically, not a global HEKB
            # backend switch.
            trajectory_object_ids: dict[str, str] = {}
            for measurement in triangulation.measurements:
                if not measurement.stabilized:
                    continue
                trajectory_object = build_hekb_object_from_trajectory(
                    measurement.run_result.trajectory,
                    session_id=str(session_id),
                    runtime_cycle_id=str(runtime_cycle_id),
                )
                stored_trajectory = await hekb.call_query("POST", "/v1/objects", json=trajectory_object)
                trajectory_object_ids[measurement.path_id] = stored_trajectory["id"]

            summary_object = build_hekb_object_from_triangulation(
                triangulation, session_id=str(session_id), runtime_cycle_id=str(runtime_cycle_id)
            )
            stored_summary = await hekb.call_query("POST", "/v1/objects", json=summary_object)
            summary_object_id = stored_summary["id"]

            for path_id, trajectory_object_id in trajectory_object_ids.items():
                await hekb.relate(trajectory_object_id, summary_object_id, "DERIVES")

            evidence_status = EvidenceStatus.PERSISTED
            evidence_object_id = summary_object_id
            invocation_result["trajectory_object_ids"] = trajectory_object_ids
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
