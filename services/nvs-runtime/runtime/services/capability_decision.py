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
    build_hekb_object_from_semantic_anchor,
    build_hekb_object_from_trajectory,
    build_hekb_object_from_triangulation,
)
from runtime.gateway.http_pool import RetryExhaustedError
from runtime.gateway.kernel_gateway import KernelGateway
from runtime.gateway.ollama_client import OllamaClient
from runtime.models.enums import RuntimeEventType
from runtime.models.schemas import EventIngestRequest
from runtime.services.event_service import EventService
from runtime.services.meaning_trajectory import build_hext_observation, run_meaning_trajectory
from runtime.services.meaning_triangulation import TriangulationInput, run_meaning_triangulation
from runtime.services.semantic_anchor import request_semantic_anchor, semantic_anchor_to_triangulation_input

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
            # ADR-0013: hekb.store() and hekb.relate() now target the same
            # backend (hekbd) by default, so a trajectory object's id is
            # always relatable — no cross-backend id mismatch to work
            # around here anymore.
            trajectory_object_ids: dict[str, str] = {}
            for measurement in triangulation.measurements:
                if not measurement.stabilized:
                    continue
                trajectory_object = build_hekb_object_from_trajectory(
                    measurement.run_result.trajectory,
                    session_id=str(session_id),
                    runtime_cycle_id=str(runtime_cycle_id),
                )
                stored_trajectory = await hekb.store(trajectory_object)
                trajectory_object_ids[measurement.path_id] = stored_trajectory["object_id"]

            summary_object = build_hekb_object_from_triangulation(
                triangulation, session_id=str(session_id), runtime_cycle_id=str(runtime_cycle_id)
            )
            stored_summary = await hekb.store(summary_object)
            summary_object_id = stored_summary["object_id"]

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


async def request_semantic_anchor_triangulation(
    db: Session,
    session_id: UUID,
    agent_id: UUID,
    observation_text: str,
    *,
    observation_id: str,
    model_id: str = "gpt-oss:20b",
    prompt_version: str = "v1",
    divergence_epsilon: float | None = None,
    capability_id: str = "semantic_anchor.triangulation",
    ollama: OllamaClient | None = None,
    hekb: HekbClient | None = None,
    event_service: EventService | None = None,
) -> CapabilityResult:
    """The Runtime Decision Boundary for GPT-OSS-as-Semantic-Anchor: a real
    generation from a real local inference runtime (`OllamaClient`,
    `runtime.services.semantic_anchor`) becomes ONE triangulation path,
    compared against a second path built directly from `observation_text`
    -- the same unmodified MeaningMapper -> MSR -> Trajectory ->
    Triangulation chain `request_meaning_triangulation()` already uses is
    called here UNCHANGED, not reimplemented. GPT-OSS is never the
    "correct" answer; it is one more measurement `run_meaning_triangulation`
    compares like any other path.

    Persists: the SemanticAnchor object itself (via
    `build_hekb_object_from_semantic_anchor()`), everything
    `request_meaning_triangulation()` already persists (both paths'
    trajectories, the triangulation summary, DERIVES edges from each
    trajectory to the summary), plus one additional DERIVES edge from the
    SemanticAnchor object to its own trajectory object -- so the full
    provenance chain (SemanticAnchor -> anchor trajectory -> triangulation
    summary; direct trajectory -> triangulation summary) is real HEKB
    graph structure, not only labels.

    `evidence_status` is `PERSISTED` only if every one of those writes
    succeeds, exactly like `request_meaning_triangulation()`'s own
    contract -- this function adds one more thing that can go BLOCKED
    (the anchor's own persistence/relate), it does not weaken that one.

    Failure at the GENERATION step (Ollama unreachable, model not pulled)
    is `RuntimeOutcome.INVOCATION_FAILED` -- a real, distinct outcome from
    evidence persistence failing after a successful generation.
    """
    ollama = ollama or OllamaClient()
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
                "input": {
                    "observation_id": observation_id,
                    "model_id": model_id,
                    "prompt_version": prompt_version,
                    "divergence_epsilon": divergence_epsilon,
                },
                "reason": None,
            },
        ),
    )
    runtime_cycle_id = request_ingest.event_ids[0]

    capability_descriptor: dict[str, Any] = {
        "capability_id": capability_id,
        "status": "IMPLEMENTED",
        "transport": "ollama-http",
    }
    invocation_result: dict[str, Any] | None = None
    evidence_status = EvidenceStatus.NOT_ATTEMPTED
    evidence_object_id: str | None = None

    try:
        anchor = await request_semantic_anchor(
            observation_text,
            observation_id=observation_id,
            model_id=model_id,
            prompt_version=prompt_version,
            client=ollama,
        )
    except _TRANSPORT_ERRORS:
        outcome = RuntimeOutcome.INVOCATION_FAILED
    else:
        direct_input = TriangulationInput(
            path_id="direct",
            observations=[
                build_hext_observation(
                    observation_id=f"{observation_id}-direct-{i:04d}",
                    text=observation_text,
                    state_hash=anchor.input_hash,
                    sealed_at=f"2026-08-18T06:00:{i:02d}Z",
                )
                for i in range(8)
            ],
            method="direct",
        )
        anchor_input = semantic_anchor_to_triangulation_input(anchor, path_id="gpt_oss_anchor")

        triangulation_result = await request_meaning_triangulation(
            db,
            session_id,
            agent_id,
            [direct_input, anchor_input],
            divergence_epsilon=divergence_epsilon,
            capability_id="semantic_anchor.triangulation.inner",
            hekb=hekb,
            event_service=event_service,
        )
        outcome = RuntimeOutcome.SUCCESS
        invocation_result = {
            "anchor_id": anchor.anchor_id,
            "model_id": anchor.model_id,
            "model_revision": anchor.model_revision,
            "structured_result": anchor.structured_result,
            "reproducibility": anchor.reproducibility,
            "triangulation": triangulation_result.invocation_result,
            "triangulation_evidence_status": triangulation_result.evidence_status.value,
        }

        if triangulation_result.evidence_status == EvidenceStatus.PERSISTED:
            try:
                anchor_object = build_hekb_object_from_semantic_anchor(
                    anchor, session_id=str(session_id), runtime_cycle_id=str(runtime_cycle_id)
                )
                stored_anchor = await hekb.store(anchor_object)
                anchor_object_id = stored_anchor["object_id"]

                anchor_trajectory_id = (
                    (triangulation_result.invocation_result or {})
                    .get("trajectory_object_ids", {})
                    .get("gpt_oss_anchor")
                )
                if anchor_trajectory_id:
                    await hekb.relate(anchor_object_id, anchor_trajectory_id, "DERIVES")

                evidence_status = EvidenceStatus.PERSISTED
                evidence_object_id = triangulation_result.evidence_object_id
                invocation_result["anchor_object_id"] = anchor_object_id
            except _TRANSPORT_ERRORS:
                evidence_status = EvidenceStatus.BLOCKED
        else:
            evidence_status = triangulation_result.evidence_status

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
