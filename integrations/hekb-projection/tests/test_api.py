from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version() -> None:
    response = client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "hekb-runtime"
    assert body["version"] == "0.1.0"


def test_storage_profile() -> None:
    response = client.get("/storage/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["storage_class"] == "in_memory"
    assert body["capabilities"]["sequential_scan"] is True
    assert body["capabilities"]["transactions"] is False
