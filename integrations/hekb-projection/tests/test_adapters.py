import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage.adapters.in_memory import InMemoryAdapter
from app.storage.adapters.minio import MinIOAdapter
from app.storage.adapters.postgres import PostgresAdapter
from app.storage.adapters.registry import AdapterRegistry
from app.storage.adapters.scylladb import ScyllaDBAdapter

client = TestClient(app)


def test_registry_resolves_known_storage_classes() -> None:
    registry = AdapterRegistry()
    assert isinstance(registry.resolve("relational"), PostgresAdapter)
    assert isinstance(registry.resolve("append_only"), ScyllaDBAdapter)
    assert isinstance(registry.resolve("blob"), MinIOAdapter)


def test_registry_falls_back_to_in_memory_for_unknown_storage_class() -> None:
    registry = AdapterRegistry()
    assert isinstance(registry.resolve("unknown"), InMemoryAdapter)
    assert isinstance(registry.resolve("some_undeclared_class"), InMemoryAdapter)


def test_stub_adapters_raise_not_implemented() -> None:
    for adapter in (PostgresAdapter(), ScyllaDBAdapter(), MinIOAdapter()):
        with pytest.raises(NotImplementedError):
            adapter.connect()
        with pytest.raises(NotImplementedError):
            adapter.write("k", b"v")
        with pytest.raises(NotImplementedError):
            adapter.read("k")


def test_stub_adapters_report_not_implemented_health() -> None:
    for adapter in (PostgresAdapter(), ScyllaDBAdapter(), MinIOAdapter()):
        health = adapter.health()
        assert health.status == "not_implemented"


def test_in_memory_adapter_round_trips_and_is_healthy() -> None:
    adapter = InMemoryAdapter()
    adapter.connect()
    assert adapter.write("k", b"v") is True
    assert adapter.read("k") == b"v"
    assert adapter.read("missing") is None
    assert adapter.health().status == "healthy"


def test_get_adapters_endpoint() -> None:
    response = client.get("/adapters")
    assert response.status_code == 200
    body = response.json()
    assert body["relational"] == "PostgresAdapter"
    assert body["append_only"] == "ScyllaDBAdapter"
    assert body["blob"] == "MinIOAdapter"
    assert body["unknown"] == "InMemoryAdapter"


def test_get_adapters_health_endpoint() -> None:
    response = client.get("/adapters/health")
    assert response.status_code == 200
    body = response.json()
    statuses = {entry["name"]: entry["status"] for entry in body}
    assert statuses["in_memory"] == "healthy"
    assert statuses["postgres"] == "not_implemented"
    assert statuses["scylladb"] == "not_implemented"
    assert statuses["minio"] == "not_implemented"
