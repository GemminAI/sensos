import pytest
from fastapi.testclient import TestClient

from api.server import app

EXPECTED_TOP_LEVEL_KEYS = {
    "version", "tags", "subject", "entities", "events",
    "time", "location", "reference", "interpreter", "metadata", "confidence",
}


def _fake_annotation(text: str, provider: str) -> dict:
    return {
        "version": "1.0",
        "tags": {
            "T09_strategic_interest_vector": {"security": 0.0, "economy": 0.0, "technology": 0.0, "resources": 0.0, "ideology": 0.0, "environment": 0.0},
            "T10_epistemic_confidence": 0.6,
            "T19_conflict_factuality_index": 0.1,
            "T03_predicate_type": None,
            "T07_actor_role": None,
            "T08_causality_direction": None,
            "T11_bias_component": None,
            "T16_economic_transmission_path": None,
        },
        "subject": {"primary": None, "type": None, "description": None},
        "entities": [],
        "events": [],
        "time": {"absolute": None, "relative": None, "tense": None},
        "location": {"primary": None, "type": None, "normalized": None},
        "reference": None,
        "interpreter": None,
        "metadata": {
            "annotation_id": "00000000-0000-4000-8000-000000000000",
            "created_at": "2026-07-17T00:00:00+00:00",
            "schema_version": "1.0",
            "engine": "semantic-annotator",
            "engine_version": "1.0.0",
            "provider": provider,
            "model": "fake-model-v1",
            "input_length": len(text),
        },
        "confidence": {
            "overall": {"value": 0.6, "quality": "REAL", "reason": None},
            "tags": {},
            "subject": {"value": None, "quality": "PLACEHOLDER", "reason": "text has no clear single subject"},
            "entities": {"value": None, "quality": "PLACEHOLDER", "reason": "backend did not return `entities`"},
            "events": {"value": None, "quality": "PLACEHOLDER", "reason": "backend did not return `events`"},
            "time": {"value": None, "quality": "PLACEHOLDER", "reason": "text carries no genuine temporal information"},
            "location": {"value": None, "quality": "PLACEHOLDER", "reason": "text names no place"},
        },
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("api.server.annotate_text", _fake_annotation)
    return TestClient(app)


def test_annotate_response_shape(client):
    resp = client.post("/annotate", json={"text": "hello world", "provider": "anthropic"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == EXPECTED_TOP_LEVEL_KEYS
    assert body["reference"] is None
    assert body["interpreter"] is None
    assert body["version"] == "1.0"


def test_annotate_defaults_provider_to_anthropic(client):
    resp = client.post("/annotate", json={"text": "hello world"})
    assert resp.status_code == 200
    assert resp.json()["metadata"]["provider"] == "anthropic"


def test_annotate_empty_text_is_422(client):
    resp = client.post("/annotate", json={"text": "", "provider": "anthropic"})
    assert resp.status_code == 422


def test_annotate_missing_api_key_is_503(monkeypatch):
    def raise_runtime_error(text, provider):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr("api.server.annotate_text", raise_runtime_error)
    resp = TestClient(app).post("/annotate", json={"text": "hello", "provider": "anthropic"})
    assert resp.status_code == 503


def test_annotate_backend_failure_is_502(monkeypatch):
    def raise_runtime_error(text, provider):
        raise RuntimeError("HTTP error 500: internal server error")

    monkeypatch.setattr("api.server.annotate_text", raise_runtime_error)
    resp = TestClient(app).post("/annotate", json={"text": "hello", "provider": "anthropic"})
    assert resp.status_code == 502


def test_annotate_malformed_backend_json_is_422(monkeypatch):
    def raise_value_error(text, provider):
        raise ValueError("No JSON object found in response")

    monkeypatch.setattr("api.server.annotate_text", raise_value_error)
    resp = TestClient(app).post("/annotate", json={"text": "hello", "provider": "anthropic"})
    assert resp.status_code == 422
