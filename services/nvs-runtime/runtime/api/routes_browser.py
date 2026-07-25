"""Browser RC-1/2 API: generate pipeline + state queries."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from runtime.api.deps import get_db
from runtime.models.schemas import (
    GenerateRequest,
    GenerateResponse,
    StateDiffResponse,
    StateListItem,
    StateNeighborsResponse,
    StateResponse,
    TimelineItem,
)
from runtime.services.crystallizer import diffusion_display_label, schema_display_version
from runtime.services.diff_service import DiffService
from runtime.services.pipeline import NarrativePipeline
from runtime.services.state_service import StateService

generate_router = APIRouter()
states_router = APIRouter()

pipeline = NarrativePipeline()
state_service = StateService()
diff_service = DiffService(state_service)

TIMELINE_ORIGINS = {"jp", "us", "cn", "eu", "uk", "qa"}


@generate_router.post("/generate", response_model=GenerateResponse, status_code=201)
async def generate_narrative_state(data: GenerateRequest, db: Session = Depends(get_db)):
    result = await pipeline.run(db, data.article, origin=data.origin)
    return GenerateResponse(**result)


@states_router.get("/states/timeline", response_model=list[TimelineItem])
def list_timeline(
    limit: int = Query(100, ge=1, le=200),
    origin: str | None = Query(None),
    db: Session = Depends(get_db),
):
    origin_filter = origin.strip().lower() if origin else None
    if origin_filter and origin_filter not in TIMELINE_ORIGINS:
        origin_filter = None
    rows = state_service.list_timeline(db, limit=limit, origin=origin_filter)
    return [
        TimelineItem(
            state_hash=r.state_hash,
            created_at=r.created_at,
            subject_origin=r.subject_origin,
            schema_version=schema_display_version(r.schema_version),
            epistemic_diffusion_state=diffusion_display_label(r.epistemic_diffusion_state),
        )
        for r in rows
    ]


@states_router.get("/states/{state_hash}/neighbors", response_model=StateNeighborsResponse)
def get_state_neighbors(state_hash: str, db: Session = Depends(get_db)):
    previous, next_hash = state_service.get_neighbors(db, state_hash)
    return StateNeighborsResponse(previous=previous, next=next_hash)


@states_router.get("/states/{state_hash}/diff", response_model=StateDiffResponse)
def get_state_diff(state_hash: str, db: Session = Depends(get_db)):
    return diff_service.compute_diff(db, state_hash)


@states_router.get("/states", response_model=list[StateListItem])
def list_states(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows = state_service.list_states(db, limit=limit, offset=offset)
    return [
        StateListItem(
            state_hash=r.state_hash,
            subject_origin=r.subject_origin,
            created_at=r.created_at,
            schema_version=r.schema_version,
            epistemic_diffusion_state=r.epistemic_diffusion_state,
        )
        for r in rows
    ]


@states_router.get("/states/{state_hash}", response_model=StateResponse)
def get_state(state_hash: str, db: Session = Depends(get_db)):
    row = state_service.get_state(db, state_hash)
    return StateResponse(**row.to_dict())
