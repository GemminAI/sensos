from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from runtime.gateway.kernel_gateway import KernelGateway
from runtime.models.enums import ForwardStatus, RuntimeEventType
from runtime.models.schemas import AgentCreate, EventIngestRequest, SessionCreate
from runtime.services.agent_service import AgentService
from runtime.services.event_service import EventService
from runtime.services.experiment_service import ExperimentService
from runtime.services.session_service import SessionService
from runtime.models.enums import AgentProvider


def test_forward_state_raw(db_session, fake_redis):
    gateway = KernelGateway()

    import httpx

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
    gateway._client = lambda: httpx.Client(transport=transport, base_url="http://k", timeout=5)

    status, ref = gateway.forward_runtime_event(
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


def test_event_ingest_pending_forward(db_session, fake_redis):
    agent_svc = AgentService()
    session_svc = SessionService()
    agent = agent_svc.create(db_session, AgentCreate(provider=AgentProvider.CUSTOM, model="m1"))
    db_session.flush()
    session = session_svc.create(db_session, SessionCreate(participants=[agent.agent_id]))
    db_session.flush()

    gateway = MagicMock()
    gateway.forward_runtime_event.return_value = (ForwardStatus.PENDING, None)
    service = EventService(gateway=gateway)

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
    assert result.forward_status == ForwardStatus.PENDING


def test_experiment_not_found(db_session):
    svc = ExperimentService()
    from runtime.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        svc.get(db_session, uuid4())
