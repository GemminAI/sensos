from datetime import datetime, timezone

import pytest

from runtime.core.exceptions import NotFoundError
from runtime.services.comparison_service import ComparisonService, _event_key
from runtime.services.crystallizer import derive_event_id


def test_derive_event_id_stable():
    article = "Same article content for multi-origin comparison."
    assert derive_event_id(article) == derive_event_id(article)
    assert derive_event_id(article).startswith("evt-")


def test_list_events_groups_by_article(db_session):
    from runtime.db.tables import NarrativeState

    article = "Shared event article text."
    event_id = derive_event_id(article)
    base = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)

    for origin in ("jp", "us", "eu"):
        db_session.add(
            NarrativeState(
                state_hash=f"hash_{origin}",
                event_id=event_id,
                narrative=f"Narrative from {origin}",
                tags={"T09": [0.1, 0.2, 0.3, 0.0, 0.0, 0.0]},
                subject_origin=origin,
                schema_version="35tag.v6.0.rc1",
                epistemic_diffusion_state="stable",
                article=article,
                provider="openai",
                created_at=base,
            )
        )
    db_session.commit()

    svc = ComparisonService()
    events = svc.list_events(db_session)
    match = [e for e in events if e["event_id"] == event_id]
    assert len(match) == 1
    assert match[0]["state_count"] == 3
    assert set(match[0]["origins"]) == {"jp", "us", "eu"}


def test_compare_filters_origins(db_session):
    from runtime.db.tables import NarrativeState

    article = "Compare filter article."
    event_id = derive_event_id(article)
    base = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)

    for origin in ("jp", "us", "cn"):
        db_session.add(
            NarrativeState(
                state_hash=f"cmp_{origin}",
                event_id=event_id,
                narrative=f"Text {origin}",
                tags={"T09": [0.0, 0.0, 0.5, 0.0, 0.0, 0.0]},
                subject_origin=origin,
                schema_version="35tag.v6.0.rc1",
                epistemic_diffusion_state="diffuse" if origin == "us" else "stable",
                article=article,
                provider="openai",
                created_at=base,
            )
        )
    db_session.commit()

    svc = ComparisonService()
    result = svc.compare(db_session, event_id, origins=["jp", "us"])
    assert len(result["states"]) == 2
    origins = {s["origin"] for s in result["states"]}
    assert origins == {"jp", "us"}


def test_compare_not_found(db_session):
    svc = ComparisonService()
    with pytest.raises(NotFoundError):
        svc.compare(db_session, "evt-missing")


def test_event_key_fallback():
    from runtime.db.tables import NarrativeState

    row = NarrativeState(
        state_hash="x",
        narrative="n",
        tags={},
        subject_origin="us",
        schema_version="35tag.v6.0.rc1",
        epistemic_diffusion_state="stable",
        article="fallback article",
        provider="openai",
    )
    assert _event_key(row) == derive_event_id("fallback article")
