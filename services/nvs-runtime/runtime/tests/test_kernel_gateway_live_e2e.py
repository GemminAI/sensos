"""End-to-end verification of the Observation Runtime -> KernelGateway ->
canonical NVS-Kernel contract fix, against a real live nvs-kernel process
(no mocks). Skips automatically if no live kernel is reachable at
NVS_KERNEL_URL, so it never blocks the regular unit test run.

    Observation Runtime (EventService.ingest)
          -> KernelGateway.forward_runtime_event
          -> Canonical NVS-Kernel (live /observe)
          -> ObserveResponse
          -> KernelGateway
          -> Runtime Event (forward_status=FORWARDED)
"""

import os
from uuid import uuid4

import pytest

from runtime.core.config import Settings
from runtime.gateway.kernel_gateway import KernelGateway
from runtime.models.enums import ForwardStatus, RuntimeEventType
from runtime.models.schemas import AgentCreate, EventIngestRequest, SessionCreate
from runtime.services.agent_service import AgentService
from runtime.services.event_service import EventService
from runtime.services.session_service import SessionService

LIVE_KERNEL_URL = os.environ.get("NVS_KERNEL_URL_LIVE", "http://127.0.0.1:18100")


def _live_gateway() -> KernelGateway | None:
    gateway = KernelGateway(settings=Settings(nvs_kernel_url=LIVE_KERNEL_URL, redis_url="redis://localhost:6379/15"))
    if not gateway.health_check():
        return None
    return gateway


def test_full_chain_against_live_canonical_kernel(db_session, fake_redis):
    gateway = _live_gateway()
    if gateway is None:
        pytest.skip(f"no live nvs-kernel reachable at {LIVE_KERNEL_URL}")

    agent_svc = AgentService()
    session_svc = SessionService()
    from runtime.models.enums import AgentProvider

    agent = agent_svc.create(db_session, AgentCreate(provider=AgentProvider.CUSTOM, model="e2e-verify"))
    db_session.flush()
    session = session_svc.create(db_session, SessionCreate(participants=[agent.agent_id]))
    db_session.flush()

    service = EventService(gateway=gateway)
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

    assert result.forward_status == ForwardStatus.FORWARDED
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
    assert result2.forward_status == ForwardStatus.FORWARDED
    events = service.list_events(db_session, session.session_id)
    assert int(events[1].kernel_run_id) > int(events[0].kernel_run_id)
