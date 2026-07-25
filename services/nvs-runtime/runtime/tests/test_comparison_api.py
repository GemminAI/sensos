from datetime import datetime, timezone

import pytest

from runtime.db.tables import NarrativeState
from runtime.services.crystallizer import derive_event_id


def _seed_event(db, article: str, origins: list[tuple[str, str, str]]):
    event_id = derive_event_id(article)
    base = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
    for origin, diffusion, sh in origins:
        db.add(
            NarrativeState(
                state_hash=sh,
                event_id=event_id,
                narrative=f"Narrative for {origin} perspective.",
                tags={"T09": [0.1, 0.2, 0.31, 0.0, 0.0, 0.0]},
                subject_origin=origin,
                schema_version="35tag.v6.0.rc1",
                epistemic_diffusion_state=diffusion,
                article=article,
                provider="openai",
                created_at=base,
            )
        )
    db.commit()
    return event_id


@pytest.fixture()
def comparison_event(db_session):
    article = "Semiconductor export policy analysis event."
    return _seed_event(
        db_session,
        article,
        [
            ("jp", "stable", "hash_jp_evt"),
            ("us", "diffuse", "hash_us_evt"),
            ("eu", "high_conflict", "hash_eu_evt"),
        ],
    )


def test_events_list_api(client, comparison_event):
    resp = client.get("/events")
    assert resp.status_code == 200
    data = resp.json()
    assert any(e["event_id"] == comparison_event for e in data)
    item = next(e for e in data if e["event_id"] == comparison_event)
    assert item["state_count"] == 3
    assert set(item["origins"]) == {"jp", "us", "eu"}
    assert "latest_created_at" in item


def test_compare_api(client, comparison_event):
    resp = client.get(f"/events/{comparison_event}/compare")
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_id"] == comparison_event
    assert len(data["states"]) == 3
    labels = {s["origin"]: s["epistemic_diffusion_state"] for s in data["states"]}
    assert labels["jp"] == "Crystallized"
    assert labels["us"] == "Diffused"
    assert labels["eu"] == "Polarized"


def test_compare_origin_filter(client, comparison_event):
    resp = client.get(f"/events/{comparison_event}/compare?origins=jp&origins=us")
    assert resp.status_code == 200
    origins = {s["origin"] for s in resp.json()["states"]}
    assert origins == {"jp", "us"}


def test_compare_not_found(client):
    resp = client.get("/events/evt-doesnotexist/compare")
    assert resp.status_code == 404
