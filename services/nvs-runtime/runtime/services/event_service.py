from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from runtime.core.exceptions import ConflictError, NotFoundError
from runtime.db.tables import Agent, Event, Session as SessionModel
from runtime.gateway.kernel_gateway import KernelGateway
from runtime.models.enums import ForwardStatus, SCHEMA_VERSION
from runtime.models.schemas import EventIngestRequest, EventIngestResponse, EventResponse
from runtime.services.redis_service import RedisService
from runtime.validators.sep_validator import validate_sep_event


class EventService:
    def __init__(
        self,
        redis: RedisService | None = None,
        gateway: KernelGateway | None = None,
    ):
        self.redis = redis or RedisService()
        self.gateway = gateway or KernelGateway()

    def ingest(
        self,
        db: Session,
        session_id: UUID,
        data: EventIngestRequest,
    ) -> EventIngestResponse:
        session = db.get(SessionModel, session_id)
        if not session:
            raise NotFoundError("ERROR_SESSION_NOT_FOUND", f"Session {session_id} not found")

        agent = db.get(Agent, data.agent_id)
        if not agent:
            raise NotFoundError("ERROR_AGENT_NOT_FOUND", f"Agent {data.agent_id} not found")

        event_id = uuid4()
        if self.redis.is_duplicate(event_id):
            raise ConflictError("ERROR_DUPLICATE_EVENT", f"Duplicate event {event_id}")

        sequence_id = self.redis.next_sequence(session_id, data.agent_id)
        source_provider = data.source_provider or agent.provider
        source_model = data.source_model or agent.model

        envelope: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "event_id": str(event_id),
            "event_type": str(data.event_type),
            "experiment_id": str(data.experiment_id) if data.experiment_id else None,
            "session_id": str(session_id),
            "agent_id": str(data.agent_id),
            "source_provider": source_provider,
            "source_model": source_model,
            "parent_event_id": str(data.parent_event_id) if data.parent_event_id else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sequence_id": sequence_id,
            "correlation_id": data.correlation_id,
            "payload": data.payload,
        }

        sep_event_type = validate_sep_event(envelope)

        forward_status, kernel_ref = self.gateway.forward_runtime_event(envelope)
        if forward_status == ForwardStatus.PENDING:
            self.redis.enqueue_forward({"event_id": str(event_id), "envelope": envelope})

        event = Event(
            event_id=event_id,
            schema_version=SCHEMA_VERSION,
            event_type=str(data.event_type),
            experiment_id=data.experiment_id,
            session_id=session_id,
            agent_id=data.agent_id,
            source_provider=source_provider,
            source_model=source_model,
            parent_event_id=data.parent_event_id,
            sequence_id=sequence_id,
            correlation_id=data.correlation_id,
            sep_event_type=sep_event_type,
            payload=data.payload,
            forward_status=forward_status.value,
            kernel_run_id=kernel_ref,
        )
        db.add(event)
        db.flush()

        self.redis.append_event_stream(session_id, envelope)
        self.redis.publish_telemetry(session_id, envelope)

        return EventIngestResponse(
            accepted=1,
            event_ids=[event_id],
            forward_status=forward_status,
        )

    def list_events(
        self,
        db: Session,
        session_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EventResponse]:
        session = db.get(SessionModel, session_id)
        if not session:
            raise NotFoundError("ERROR_SESSION_NOT_FOUND", f"Session {session_id} not found")
        events = (
            db.query(Event)
            .filter(Event.session_id == session_id)
            .order_by(Event.sequence_id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_response(e) for e in events]

    @staticmethod
    def _to_response(event: Event) -> EventResponse:
        return EventResponse(
            event_id=event.event_id,
            schema_version=event.schema_version,
            event_type=event.event_type,
            experiment_id=event.experiment_id,
            session_id=event.session_id,
            agent_id=event.agent_id,
            source_provider=event.source_provider,
            source_model=event.source_model,
            parent_event_id=event.parent_event_id,
            sequence_id=event.sequence_id,
            sep_event_type=event.sep_event_type,
            payload=event.payload or {},
            forward_status=event.forward_status,
            kernel_run_id=event.kernel_run_id,
            created_at=event.created_at,
        )
