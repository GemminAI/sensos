from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from runtime.api.deps import get_db
from runtime.models.schemas import (
    AgentCreate,
    AgentResponse,
    CapabilitiesResponse,
    EventIngestRequest,
    EventIngestResponse,
    EventResponse,
    ExperimentCreate,
    ExperimentResponse,
    SessionCreate,
    SessionJoin,
    SessionResponse,
)
from runtime.services.agent_service import AgentService
from runtime.services.event_service import EventService
from runtime.services.experiment_service import ExperimentService
from runtime.services.redis_service import RedisService
from runtime.services.session_service import SessionService
from runtime.services.stream_service import StreamService

router = APIRouter()

agent_service = AgentService()
session_service = SessionService()
experiment_service = ExperimentService()
event_service = EventService()
stream_service = StreamService()
redis_service = RedisService()


@router.post("/agents", response_model=AgentResponse, status_code=201)
def create_agent(data: AgentCreate, db: Session = Depends(get_db)):
    return agent_service.create(db, data)


@router.get("/agents", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db)):
    return agent_service.list_agents(db)


@router.get("/agents/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: UUID, db: Session = Depends(get_db)):
    return agent_service.get(db, agent_id)


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session(data: SessionCreate, db: Session = Depends(get_db)):
    result = session_service.create(db, data)
    redis_service.set_session_cache(result.session_id, {"status": result.status, "label": result.label})
    return result


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: UUID, db: Session = Depends(get_db)):
    return session_service.get(db, session_id)


@router.post("/sessions/{session_id}/join", response_model=SessionResponse)
def join_session(session_id: UUID, data: SessionJoin, db: Session = Depends(get_db)):
    return session_service.join(db, session_id, data)


@router.post("/sessions/{session_id}/experiments", response_model=ExperimentResponse, status_code=201)
def create_experiment(session_id: UUID, data: ExperimentCreate, db: Session = Depends(get_db)):
    result = experiment_service.create(db, session_id, data)
    redis_service.set_experiment_cache(result.experiment_id, {"status": result.status, "session_id": str(session_id)})
    return result


@router.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(experiment_id: UUID, db: Session = Depends(get_db)):
    return experiment_service.get(db, experiment_id)


@router.post("/sessions/{session_id}/events", response_model=EventIngestResponse, status_code=202)
def ingest_event(session_id: UUID, data: EventIngestRequest, db: Session = Depends(get_db)):
    return event_service.ingest(db, session_id, data)


@router.get("/sessions/{session_id}/events", response_model=list[EventResponse])
def query_events(
    session_id: UUID,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return event_service.list_events(db, session_id, limit=limit, offset=offset)


@router.get("/sessions/{session_id}/stream")
async def stream_events(
    session_id: UUID,
    replay_from: str = Query("0-0"),
):
    return StreamingResponse(
        stream_service.sse_stream(session_id, replay_from=replay_from),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/capabilities", response_model=CapabilitiesResponse)
def capabilities():
    return CapabilitiesResponse(
        service="nvs-runtime",
        version="0.1.0-p1",
        rfc="RFC-NVS42 v0.3",
        features=[
            "agent_registry",
            "session_registry",
            "experiment_registry",
            "sep_validation",
            "event_persistence",
            "event_streaming",
            "kernel_forwarding",
            "mcp_tools",
        ],
        mcp_tools=[
            "nvs_register_agent",
            "nvs_create_session",
            "nvs_emit_sep_event",
            "nvs_query_events",
        ],
        layer3_stubs=[
            "nvs_forecast_transition",
            "nvs_check_integrity",
            "nvs_get_alignment_profile",
            "nvs_check_boundary_status",
        ],
    )
