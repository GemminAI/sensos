from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from runtime.db.tables import NarrativeState
from runtime.services.crystallizer import diffusion_display_label, schema_display_version


def _insert_state(db, *, state_hash: str, origin: str, created_at: datetime, diffusion: str = "stable"):
    row = NarrativeState(
        state_hash=state_hash,
        narrative=f"Narrative for {state_hash}",
        tags={"T10": 0.8, "T19": 0.1},
        subject_origin=origin,
        schema_version="35tag.v6.0.rc1",
        epistemic_diffusion_state=diffusion,
        article="article",
        provider="openai",
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def seeded_states(db_session):
    base = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
    states = [
        _insert_state(db_session, state_hash="hash_newest", origin="us", created_at=base),
        _insert_state(db_session, state_hash="hash_middle", origin="us", created_at=base - timedelta(hours=1)),
        _insert_state(db_session, state_hash="hash_oldest", origin="us", created_at=base - timedelta(hours=2)),
        _insert_state(db_session, state_hash="hash_jp", origin="jp", created_at=base - timedelta(minutes=30)),
    ]
    db_session.commit()
    return states


def test_timeline_api_returns_desc_order(client, seeded_states):
    resp = client.get("/states/timeline?limit=100")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    assert data[0]["state_hash"] == "hash_newest"
    assert data[-1]["state_hash"] == "hash_oldest"
    assert data[0]["schema_version"] == "6.0.0"
    assert data[0]["epistemic_diffusion_state"] == "Crystallized"


def test_timeline_origin_filter(client, seeded_states):
    resp = client.get("/states/timeline?origin=jp")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["state_hash"] == "hash_jp"
    assert data[0]["subject_origin"] == "jp"


def test_timeline_invalid_origin_ignored(client, seeded_states):
    resp = client.get("/states/timeline?origin=invalid")
    assert resp.status_code == 200
    assert len(resp.json()) == 4


def test_neighbors_api(client, seeded_states):
    resp = client.get("/states/hash_middle/neighbors")
    assert resp.status_code == 200
    data = resp.json()
    assert data["previous"] == "hash_oldest"
    assert data["next"] == "hash_newest"


def test_neighbors_edges(client, seeded_states):
    newest = client.get("/states/hash_newest/neighbors").json()
    assert newest["next"] is None
    assert newest["previous"] == "hash_middle"

    oldest = client.get("/states/hash_oldest/neighbors").json()
    assert oldest["previous"] is None
    assert oldest["next"] == "hash_middle"


def test_neighbors_not_found(client):
    resp = client.get("/states/doesnotexist/neighbors")
    assert resp.status_code == 404


def test_diffusion_display_labels():
    assert diffusion_display_label("stable") == "Crystallized"
    assert diffusion_display_label("high_conflict") == "Polarized"
    assert schema_display_version("35tag.v6.0.rc1") == "6.0.0"


@pytest.mark.asyncio
async def test_timeline_after_generate(client, mock_annotator):
    with patch(
        "runtime.services.pipeline.generate_narrative",
        new=AsyncMock(return_value=("Timeline narrative.", "openai")),
    ):
        create = client.post(
            "/runtime/generate",
            json={"article": "Timeline test article.", "origin": "us"},
        )
    assert create.status_code == 201
    state_hash = create.json()["state_hash"]

    timeline = client.get("/states/timeline")
    assert timeline.status_code == 200
    hashes = [item["state_hash"] for item in timeline.json()]
    assert state_hash in hashes

    neighbors = client.get(f"/states/{state_hash}/neighbors")
    assert neighbors.status_code == 200
    assert "previous" in neighbors.json()
    assert "next" in neighbors.json()
