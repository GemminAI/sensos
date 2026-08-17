"""End-to-end verification of the Observation Runtime -> KernelGateway ->
canonical NVS-Kernel contract, against a real live nvs-kernel process (no
mocks). Skips automatically if no live kernel is reachable at
NVS_KERNEL_URL_LIVE, so it never blocks the regular unit test run.

EXP-Ubuntu011: the chain is now fully async / queue-first —

    Observation Runtime (EventService.ingest) -> Queue (Redis stream,
    forward_status=QUEUED in the response) -> ForwardWorker.drain_once()
    -> KernelGateway.observe_batch -> Canonical NVS-Kernel (live /observe)
    -> ObserveResponse -> Runtime Event (forward_status=FORWARDED)

`service.ingest()` alone no longer proves delivery (it only enqueues); this
test drives the worker's drain_once() once, synchronously, to observe the
same transition the background task performs continuously in production.
"""

import os
from contextlib import nullcontext
from uuid import uuid4

import pytest

from runtime.core.config import Settings
from runtime.gateway.kernel_gateway import KernelGateway
from runtime.models.enums import ForwardStatus, RuntimeEventType
from runtime.models.schemas import AgentCreate, EventIngestRequest, SessionCreate
from runtime.services.agent_service import AgentService
from runtime.services.event_service import EventService
from runtime.services.forward_worker import ForwardWorker
from runtime.services.session_service import SessionService

LIVE_KERNEL_URL = os.environ.get("NVS_KERNEL_URL_LIVE", "http://127.0.0.1:18100")


async def _live_gateway() -> KernelGateway | None:
    gateway = KernelGateway(settings=Settings(nvs_kernel_url=LIVE_KERNEL_URL, redis_url="redis://localhost:6379/15"))
    if not await gateway.health_check():
        return None
    return gateway


async def test_full_chain_against_live_canonical_kernel(db_session, fake_redis):
    gateway = await _live_gateway()
    if gateway is None:
        pytest.skip(f"no live nvs-kernel reachable at {LIVE_KERNEL_URL}")

    agent_svc = AgentService()
    session_svc = SessionService()
    from runtime.models.enums import AgentProvider

    agent = agent_svc.create(db_session, AgentCreate(provider=AgentProvider.CUSTOM, model="e2e-verify"))
    db_session.flush()
    session = session_svc.create(db_session, SessionCreate(participants=[agent.agent_id]))
    db_session.flush()

    service = EventService()
    # Same db_session the test uses, not the process-global engine — see
    # ForwardWorker.db_session_factory docstring.
    worker = ForwardWorker(gateway=gateway, db_session_factory=lambda: nullcontext(db_session))

    result = service.ingest(
        db_session,
        session.session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.STATE_RAW.value,
            agent_id=agent.agent_id,
            source_provider="custom",
            payload={"text": "e2e verification: real state observation"},
        ),
    )
    assert result.forward_status == ForwardStatus.QUEUED

    processed = await worker.drain_once(block_ms=100)
    assert processed == 1

    stored = service.list_events(db_session, session.session_id)[0]
    assert stored.forward_status == ForwardStatus.FORWARDED.value
    assert stored.kernel_run_id is not None
    assert stored.kernel_run_id.isdigit()  # cycle counter from the real kernel

    # Second event on the same session -> cycle must advance, proving this
    # is a real, stateful kernel session and not a stub.
    from runtime.models.enums import SEP_VERSION

    result2 = service.ingest(
        db_session,
        session.session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.SEP_EXCITATION.value,
            agent_id=agent.agent_id,
            source_provider="custom",
            payload={
                "sep_version": SEP_VERSION,
                "event_id": str(uuid4()),
                "event_type": "excitation.step",
                "timestamp": "2026-07-31T00:00:00.000Z",
                "payload": {"amplitude": 0.5, "basis": "35TAG", "duration": 50},
                "text": "e2e verification: injected excitation",
            },
        ),
    )
    assert result2.forward_status == ForwardStatus.QUEUED
    await worker.drain_once(block_ms=100)

    events = service.list_events(db_session, session.session_id)
    assert events[1].forward_status == ForwardStatus.FORWARDED.value
    assert int(events[1].kernel_run_id) > int(events[0].kernel_run_id)


async def test_invoke_port_against_live_canonical_kernel():
    """KernelGateway.invoke_port() against a real, live nvs-kernel's
    POST /ports/{port_id}_Port/invoke — no mocks. Skips automatically if no
    live kernel is reachable at NVS_KERNEL_URL_LIVE, same as the rest of
    this file.

    Uses P04, a real stateless Port (no session_id required) with the exact
    field shape previously captured working against the shared GCP
    deployment (Projects/sensos/experiments/
    EXP-TRJ-38PORT-SEMANTIC-PERTURBATION-001/code/collector.py's
    STATELESS["P04"]) — not a guessed request shape.
    """
    gateway = await _live_gateway()
    if gateway is None:
        pytest.skip(f"no live nvs-kernel reachable at {LIVE_KERNEL_URL}")

    result = await gateway.invoke_port("P04", {"vector": [1.0, 2.0, 3.0]})
    assert isinstance(result, dict)


async def test_get_port_capability_against_live_canonical_kernel():
    """KernelGateway.get_port_capability() against a real, live nvs-kernel's
    GET /ports/{port_id}_Port — no mocks. Skips automatically if no live
    kernel is reachable, same as the rest of this file.
    """
    gateway = await _live_gateway()
    if gateway is None:
        pytest.skip(f"no live nvs-kernel reachable at {LIVE_KERNEL_URL}")

    capability = await gateway.get_port_capability("P04")
    assert capability["id"] == "P04_Port"
    assert capability["status"] in ("IMPLEMENTED", "NOT_IMPLEMENTED")


async def test_request_capability_against_live_canonical_kernel(db_session, fake_redis):
    """Runtime Decision Boundary (runtime/services/capability_decision.py)
    end-to-end: real SQLite test DB + fake Redis (this repo's own test
    convention for DB/queue infrastructure — see
    test_full_chain_against_live_canonical_kernel above) + a REAL, LIVE
    KernelGateway and a REAL HekbClient (default settings — genuinely
    unreachable, not mocked). Proves the orchestration logic drives a real
    external Port call correctly, and that HEKB's real unavailability is
    reported honestly as BLOCKED evidence, not silently converted to
    success. Skips automatically if no live kernel is reachable.
    """
    from runtime.gateway.hekb_client import HekbClient
    from runtime.services.capability_decision import (
        CapabilityRequest,
        EvidenceStatus,
        RuntimeOutcome,
        request_capability,
    )

    gateway = await _live_gateway()
    if gateway is None:
        pytest.skip(f"no live nvs-kernel reachable at {LIVE_KERNEL_URL}")

    agent_svc = AgentService()
    session_svc = SessionService()
    from runtime.models.enums import AgentProvider

    agent = agent_svc.create(db_session, AgentCreate(provider=AgentProvider.CUSTOM, model="e2e-verify"))
    db_session.flush()
    session = session_svc.create(db_session, SessionCreate(participants=[agent.agent_id]))
    db_session.flush()

    result = await request_capability(
        db_session,
        session.session_id,
        agent.agent_id,
        CapabilityRequest(capability_id="P04", input={"vector": [1.0, 2.0, 3.0]}),
        gateway=gateway,
        hekb=HekbClient(),  # real client, real (unreachable) default hekb_url
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.SUCCESS  # real live Port call succeeded
    assert result.invocation_result is not None
    assert result.evidence_status == EvidenceStatus.BLOCKED  # HEKB genuinely unreachable

    events = EventService().list_events(db_session, session.session_id)
    request_event = next(e for e in events if e.event_type == RuntimeEventType.CAPABILITY_REQUESTED.value)
    result_event = next(e for e in events if e.event_type == RuntimeEventType.CAPABILITY_RESULT.value)
    assert result_event.parent_event_id == request_event.event_id
