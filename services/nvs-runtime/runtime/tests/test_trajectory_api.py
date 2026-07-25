from datetime import datetime, timedelta, timezone

import pytest

from runtime.db.tables import NarrativeState
from runtime.services.crystallizer import derive_event_id
from runtime.services.trajectory_service import (
    TrajectoryService,
    diffusion_changes,
    duration_days,
    project_t09,
    trajectory_length,
)


def test_project_t09():
    t09 = {
        "security": 0.5,
        "economy": 0.1,
        "technology": 0.8,
        "ideology": 0.2,
        "environment": 0.3,
        "resources": 0.6,
    }
    x, y, z = project_t09(t09)
    assert x == 0.4
    assert y == 0.6
    assert z == -0.3


@pytest.fixture()
def trajectory_event(db_session):
    article = "Trajectory test article."
    event_id = derive_event_id(article)
    base = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        ("s1", "us", base, "stable", {"T09": [0.5, 0.1, 0.2, 0.0, 0.0, 0.0]}),
        ("s2", "jp", base + timedelta(days=7), "diffuse", {"T09": [0.2, 0.4, 0.6, 0.0, 0.0, 0.0]}),
        ("s3", "eu", base + timedelta(days=14), "stable", {"T09": [0.1, 0.1, 0.3, 0.0, 0.0, 0.5]}),
    ]
    for sh, origin, created, diffusion, tags in rows:
        db_session.add(
            NarrativeState(
                state_hash=sh,
                event_id=event_id,
                narrative=f"Narrative {sh}",
                tags=tags,
                subject_origin=origin,
                schema_version="35tag.v6.0.rc1",
                epistemic_diffusion_state=diffusion,
                article=article,
                provider="openai",
                created_at=created,
            )
        )
    db_session.commit()
    return event_id


def test_trajectory_api(client, trajectory_event):
    resp = client.get(f"/events/{trajectory_event}/trajectory")
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_id"] == trajectory_event
    assert len(data["points"]) == 3
    assert data["points"][0]["state_hash"] == "s1"
    assert data["points"][-1]["state_hash"] == "s3"
    assert "x" in data["points"][0]
    assert data["points"][0]["diffusion"] == "Crystallized"


def test_trajectory_not_found(client):
    resp = client.get("/events/evt-missing/trajectory")
    assert resp.status_code == 404


def test_trajectory_metrics_helpers():
    points = [
        {"x": 0.0, "y": 0.0, "z": 0.0, "diffusion": "Crystallized", "created_at": "2026-06-01T12:00:00+00:00"},
        {"x": 1.0, "y": 0.0, "z": 0.0, "diffusion": "Diffused", "created_at": "2026-06-15T12:00:00+00:00"},
    ]
    assert trajectory_length(points) == 1.0
    assert diffusion_changes(points) == 1
    assert duration_days(points) == 14


def test_trajectory_service_order(db_session, trajectory_event):
    svc = TrajectoryService()
    result = svc.get_trajectory(db_session, trajectory_event)
    hashes = [p["state_hash"] for p in result["points"]]
    assert hashes == ["s1", "s2", "s3"]
