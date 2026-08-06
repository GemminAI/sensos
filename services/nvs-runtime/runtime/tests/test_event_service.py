from uuid import uuid4

import httpx
import pytest

from runtime.gateway import http_pool
from runtime.gateway.kernel_gateway import KernelGateway
from runtime.models.enums import ForwardStatus, RuntimeEventType
from runtime.models.schemas import AgentCreate, EventIngestRequest, SessionCreate
from runtime.services.agent_service import AgentService
from runtime.services.event_service import EventService
from runtime.services.experiment_service import ExperimentService
from runtime.services.session_service import SessionService
from runtime.models.enums import AgentProvider


async def test_forward_state_raw(db_session, fake_redis, monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "session_id": "demo",
                "cycle": 1,
                "control": {
                    "tier": 0,
                    "tier_label": "L0",
                    "intervention": "MONITOR",
                    "actionable": False,
                    "requires_approval": False,
                    "authorized": True,
                    "reason": "steady at L0",
                },
            },
        )

    transport = httpx.MockTransport(handler)

    async def fake_get_pooled_client(base_url, profile=None):
        return httpx.AsyncClient(transport=transport, base_url=base_url)

    monkeypatch.setattr(http_pool, "get_pooled_client", fake_get_pooled_client)
    gateway = KernelGateway()

    status, ref = await gateway.forward_runtime_event(
        {
            "event_type": RuntimeEventType.STATE_RAW.value,
            "session_id": str(uuid4()),
            "agent_id": str(uuid4()),
            "sequence_id": 0,
            "payload": {"text": "raw state sample"},
        }
    )
    assert status == ForwardStatus.FORWARDED
    assert ref == "1"


def test_event_ingest_always_queues(db_session, fake_redis):
    """EXP-Ubuntu011: ingest() no longer calls the kernel inline — every
    event is unconditionally queued for ForwardWorker to deliver later."""
    agent_svc = AgentService()
    session_svc = SessionService()
    agent = agent_svc.create(db_session, AgentCreate(provider=AgentProvider.CUSTOM, model="m1"))
    db_session.flush()
    session = session_svc.create(db_session, SessionCreate(participants=[agent.agent_id]))
    db_session.flush()

    service = EventService()

    from runtime.models.enums import SEP_VERSION

    result = service.ingest(
        db_session,
        session.session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.SEP_EXCITATION.value,
            agent_id=agent.agent_id,
            source_provider="custom",
            payload={
                "sep_version": SEP_VERSION,
                "event_id": str(uuid4()),
                "event_type": "excitation.pulse",
                "timestamp": "2026-06-14T12:00:00.000Z",
                "payload": {"amplitude": 0.3, "basis": "35TAG"},
            },
        ),
    )
    assert result.forward_status == ForwardStatus.QUEUED

    queued = fake_redis.xrange("runtime:forward:queue")
    assert len(queued) == 1


def test_experiment_not_found(db_session):
    svc = ExperimentService()
    from runtime.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        svc.get(db_session, uuid4())
