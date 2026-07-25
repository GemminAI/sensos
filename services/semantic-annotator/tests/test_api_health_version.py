from fastapi.testclient import TestClient

from api.server import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_version():
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["engine"] == "semantic-annotator"
    assert body["schema_version"] == "1.0"
    assert "engine_version" in body


def test_openapi_json_lists_annotate():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/annotate" in resp.json()["paths"]


def test_docs_and_redoc_render():
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
