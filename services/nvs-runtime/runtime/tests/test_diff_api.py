from datetime import datetime, timedelta, timezone

import pytest

from runtime.db.tables import NarrativeState


def _insert_state(
    db,
    *,
    state_hash: str,
    origin: str,
    created_at: datetime,
    narrative: str,
    tags: dict | None = None,
    diffusion: str = "stable",
    schema_version: str = "35tag.v6.0.rc1",
):
    row = NarrativeState(
        state_hash=state_hash,
        narrative=narrative,
        tags=tags or {"T09": [0.0, 0.0, 0.31, 0.0, 0.0, 0.0], "T10": 0.8, "T19": 0.1},
        subject_origin=origin,
        schema_version=schema_version,
        epistemic_diffusion_state=diffusion,
        article="article",
        provider="openai",
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def diff_pair(db_session):
    base = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
    _insert_state(
        db_session,
        state_hash="prev_hash",
        origin="us",
        created_at=base - timedelta(hours=1),
        narrative="Semiconductor policy remains stable with moderate growth.",
        tags={"T09": [0.0, 0.0, 0.31, 0.0, 0.0, 0.0], "T10": 0.8, "T19": 0.35},
        diffusion="diffuse",
    )
    _insert_state(
        db_session,
        state_hash="curr_hash",
        origin="us",
        created_at=base,
        narrative="Semiconductor export controls expanded with rapid technology shifts.",
        tags={"T09": [0.0, 0.0, 0.62, 0.0, 0.0, 0.0], "T10": 0.8, "T19": 0.1},
        diffusion="stable",
    )
    db_session.commit()


def test_diff_api_success(client, diff_pair):
    resp = client.get("/states/curr_hash/diff")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_hash"] == "curr_hash"
    assert data["previous_hash"] == "prev_hash"
    narrative = data["narrative"]
    assert narrative["added"] or narrative["removed"] or narrative["changed"]
    assert data["tags"]["T09"]["before"]["technology"] == 0.31
    assert data["tags"]["T09"]["after"]["technology"] == 0.62
    assert data["tags"]["T22"]["before"] == "Diffused"
    assert data["tags"]["T22"]["after"] == "Crystallized"


def test_diff_api_no_previous(client, db_session):
    base = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
    _insert_state(
        db_session,
        state_hash="only_one",
        origin="us",
        created_at=base,
        narrative="Single state narrative.",
    )
    db_session.commit()

    resp = client.get("/states/only_one/diff")
    assert resp.status_code == 404


def test_diff_api_not_found(client):
    resp = client.get("/states/missing_hash/diff")
    assert resp.status_code == 404
