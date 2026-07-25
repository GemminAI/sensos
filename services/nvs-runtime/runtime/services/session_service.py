from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from runtime.core.exceptions import ConflictError, NotFoundError
from runtime.db.tables import Agent, Session as SessionModel, SessionParticipant
from runtime.models.schemas import SessionCreate, SessionJoin, SessionResponse


class SessionService:
    def create(self, db: Session, data: SessionCreate) -> SessionResponse:
        session = SessionModel(label=data.label, options=data.options)
        db.add(session)
        db.flush()
        for agent_id in data.participants:
            self._ensure_agent(db, agent_id)
            db.add(SessionParticipant(session_id=session.session_id, agent_id=agent_id, role="participant"))
        db.flush()
        return self._to_response(db, session)

    def get(self, db: Session, session_id: UUID) -> SessionResponse:
        session = db.get(SessionModel, session_id)
        if not session:
            raise NotFoundError("ERROR_SESSION_NOT_FOUND", f"Session {session_id} not found")
        return self._to_response(db, session)

    def join(self, db: Session, session_id: UUID, data: SessionJoin) -> SessionResponse:
        session = db.get(SessionModel, session_id)
        if not session:
            raise NotFoundError("ERROR_SESSION_NOT_FOUND", f"Session {session_id} not found")
        if session.status == "closed":
            raise ConflictError("ERROR_SESSION_CLOSED", "Cannot join closed session")
        self._ensure_agent(db, data.agent_id)
        existing = db.get(SessionParticipant, {"session_id": session_id, "agent_id": data.agent_id})
        if existing and existing.left_at is None:
            return self._to_response(db, session)
        if existing:
            existing.left_at = None
            existing.role = data.role
            existing.joined_at = datetime.now(timezone.utc)
        else:
            db.add(SessionParticipant(session_id=session_id, agent_id=data.agent_id, role=data.role))
        db.flush()
        return self._to_response(db, session)

    @staticmethod
    def _ensure_agent(db: Session, agent_id: UUID) -> Agent:
        agent = db.get(Agent, agent_id)
        if not agent:
            raise NotFoundError("ERROR_AGENT_NOT_FOUND", f"Agent {agent_id} not found")
        return agent

    @staticmethod
    def _to_response(db: Session, session: SessionModel) -> SessionResponse:
        participants = (
            db.query(SessionParticipant)
            .filter(SessionParticipant.session_id == session.session_id, SessionParticipant.left_at.is_(None))
            .all()
        )
        return SessionResponse(
            session_id=session.session_id,
            label=session.label,
            status=session.status,
            kernel_run_ids=session.kernel_run_ids or {},
            options=session.options or {},
            created_at=session.created_at,
            closed_at=session.closed_at,
            participants=[
                {"agent_id": str(p.agent_id), "role": p.role, "joined_at": p.joined_at.isoformat()}
                for p in participants
            ],
        )
