import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["TESTING"] = "1"

from runtime.api import deps
from runtime.core.config import Settings
from runtime.db.tables import Base
from runtime.gateway.http_pool import close_all_pooled_clients
from runtime.main import app
from runtime.services.redis_service import RedisService


@pytest.fixture(autouse=True)
async def _reset_pooled_http_clients():
    """EXP-Ubuntu011: http_pool caches one AsyncClient per base_url for the
    process lifetime — correct in production (one long-lived event loop),
    but each test function gets its own event loop
    (asyncio_default_fixture_loop_scope=function), so a client cached by one
    test and reused by a later one fails with "Event loop is closed". Clear
    the cache around every test instead of only where http_pool is tested
    directly."""
    await close_all_pooled_clients()
    yield
    await close_all_pooled_clients()


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@pytest.fixture(scope="session")
def test_settings():
    return Settings(
        database_url="sqlite://",
        redis_url="redis://localhost:6379/15",
    )


@pytest.fixture()
def db_engine(test_settings):
    engine = create_engine(
        test_settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture()
def fake_redis(monkeypatch):
    """Patches both RedisService.client (sync) and .aclient (async,
    EXP-Ubuntu011) onto the same fakeredis FakeServer, so data enqueued via
    the sync client (EventService.ingest) is visible to the async consumer
    group reads (ForwardWorker) within one test."""
    import fakeredis

    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    aclient = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)

    monkeypatch.setattr(RedisService, "client", property(lambda self: client))
    monkeypatch.setattr(RedisService, "aclient", property(lambda self: aclient))
    return client


@pytest.fixture()
def client(db_engine, fake_redis):
    Session = sessionmaker(bind=db_engine)

    def _get_db():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[deps.get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def mock_annotator():
    """Patches SemanticAnnotatorClient.annotate so tests never make a real
    HTTP call to Semantic Annotator. Fail Fast means NarrativePipeline now
    raises (rather than silently falling back to zeroed tags) whenever
    Semantic Annotator is unreachable - any test exercising POST
    /runtime/generate must request this fixture explicitly."""
    from unittest.mock import AsyncMock, patch

    from runtime.services.semantic_annotator_client import AnnotationResult, TagsResult

    result = AnnotationResult(
        version="1.0",
        tags=TagsResult(
            t09_strategic_interest_vector={
                "security": 0.0, "economy": 0.0, "technology": 0.0,
                "resources": 0.0, "ideology": 0.0, "environment": 0.0,
            },
            t10_epistemic_confidence=0.72,
            t19_conflict_factuality_index=0.1,
        ),
        subject={"primary": None, "type": None, "description": None},
        entities=[],
        events=[],
        time={"absolute": None, "relative": None, "tense": None},
        location={"primary": None, "type": None, "normalized": None},
        metadata={
            "annotation_id": "test-annotation-id",
            "created_at": "2026-01-01T00:00:00+00:00",
            "schema_version": "1.0",
            "engine": "semantic-annotator",
            "engine_version": "1.0.0",
            "provider": "anthropic",
            "model": "test-model",
            "input_length": 10,
        },
        confidence={
            "overall": {"value": 0.72, "quality": "REAL", "reason": None},
            "tags": {},
            "subject": {"value": None, "quality": "PLACEHOLDER", "reason": None},
            "entities": {"value": None, "quality": "PLACEHOLDER", "reason": None},
            "events": {"value": None, "quality": "PLACEHOLDER", "reason": None},
            "time": {"value": None, "quality": "PLACEHOLDER", "reason": None},
            "location": {"value": None, "quality": "PLACEHOLDER", "reason": None},
        },
    )
    with patch(
        "runtime.services.semantic_annotator_client.SemanticAnnotatorClient.annotate",
        new=AsyncMock(return_value=result),
    ):
        yield result


@pytest.fixture()
def sep_payload():
    from runtime.models.enums import SEP_VERSION

    return {
        "sep_version": SEP_VERSION,
        "event_id": "660e8400-e29b-41d4-a716-446655440003",
        "event_type": "excitation.step",
        "timestamp": "2026-06-14T12:00:00.000Z",
        "payload": {"amplitude": 0.7, "basis": "35TAG", "duration": 100},
    }
