import pytest

from runtime.services.agent_service import AgentService
from runtime.services.session_service import SessionService
from runtime.models.schemas import AgentCreate, SessionCreate
from runtime.models.enums import AgentProvider
from uuid import uuid4


def test_agent_crud(db_session):
    service = AgentService()
    agent = service.create(
        db_session,
        AgentCreate(provider=AgentProvider.OPENAI, model="gpt-4", capabilities=["sep.excitation"]),
    )
    db_session.commit()
    fetched = service.get(db_session, agent.agent_id)
    assert fetched.model == "gpt-4"
    agents = service.list_agents(db_session)
    assert len(agents) == 1


def test_session_with_participants(db_session):
    agent_svc = AgentService()
    session_svc = SessionService()
    agent = agent_svc.create(db_session, AgentCreate(provider=AgentProvider.CUSTOM, model="test"))
    db_session.flush()
    session = session_svc.create(
        db_session,
        SessionCreate(label="lab", participants=[agent.agent_id]),
    )
    assert len(session.participants) == 1
