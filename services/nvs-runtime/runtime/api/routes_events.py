"""Origin comparison API — event list and multi-origin compare."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from runtime.api.deps import get_db
from runtime.models.schemas import CompareResponse, EventListItem, TrajectoryResponse
from runtime.services.comparison_service import ComparisonService
from runtime.services.trajectory_service import TrajectoryService

router = APIRouter()
comparison_service = ComparisonService()
trajectory_service = TrajectoryService(comparison_service)


@router.get("/events", response_model=list[EventListItem])
def list_events(db: Session = Depends(get_db)):
    return comparison_service.list_events(db)


@router.get("/events/{event_id}/compare", response_model=CompareResponse)
def compare_event(
    event_id: str,
    origins: list[str] | None = Query(None),
    db: Session = Depends(get_db),
):
    return comparison_service.compare(db, event_id, origins=origins)


@router.get("/events/{event_id}/trajectory", response_model=TrajectoryResponse)
def event_trajectory(event_id: str, db: Session = Depends(get_db)):
    return trajectory_service.get_trajectory(db, event_id)
