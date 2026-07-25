"""Tests for SensOS FastAPI application."""

from fastapi.testclient import TestClient

from sensos.api.app import create_app


def test_health_endpoint():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_runtime_plugins_listing():
    client = TestClient(create_app())
    response = client.get("/runtime/plugins")
    assert response.status_code == 200
    plugins = response.json()["plugins"]
    backends = {p["backend"] for p in plugins}
    assert "claude_cli" in backends
    assert "gpt" in backends


def test_kernel_cycle_mock_backend(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    client = TestClient(create_app())
    response = client.post(
        "/kernel/cycle",
        json={
            "prompt": "Evaluate safety.",
            "max_iterations": 2,
            "runtime_backend": "mock",
            "verbose": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["runtime_name"]
    assert body["steps_executed"] >= 1
