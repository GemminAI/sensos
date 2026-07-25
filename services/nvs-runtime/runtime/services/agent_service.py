from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from runtime.core.exceptions import NotFoundError
from runtime.db.tables import Agent
from runtime.models.schemas import AgentCreate, AgentResponse


class AgentService:
    def create(self, db: Session, data: AgentCreate) -> AgentResponse:
        agent = Agent(
            display_name=data.display_name,
            provider=data.provider.value,
            model=data.model,
            transport=data.transport,
            capabilities=data.capabilities,
            metadata_=data.metadata,
            last_seen_at=datetime.now(timezone.utc),
        )
        db.add(agent)
        db.flush()
        return self._to_response(agent)

    def list_agents(self, db: Session) -> list[AgentResponse]:
        agents = db.query(Agent).filter(Agent.status == "active").order_by(Agent.registered_at.desc()).all()
        return [self._to_response(a) for a in agents]

    def get(self, db: Session, agent_id: UUID) -> AgentResponse:
        agent = db.get(Agent, agent_id)
        if not agent or agent.status == "deregistered":
            raise NotFoundError("ERROR_AGENT_NOT_FOUND", f"Agent {agent_id} not found")
        return self._to_response(agent)

    def touch(self, db: Session, agent_id: UUID) -> None:
        agent = db.get(Agent, agent_id)
        if agent:
            agent.last_seen_at = datetime.now(timezone.utc)

    @staticmethod
    def _to_response(agent: Agent) -> AgentResponse:
        return AgentResponse(
            agent_id=agent.agent_id,
            display_name=agent.display_name,
            provider=agent.provider,
            model=agent.model,
            transport=agent.transport,
            capabilities=agent.capabilities if isinstance(agent.capabilities, list) else [],
            status=agent.status,
            metadata=agent.metadata_ or {},
            registered_at=agent.registered_at,
            last_seen_at=agent.last_seen_at,
        )
