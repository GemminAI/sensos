"""Stream runtime and API tests."""

import time

import pytest
from fastapi.testclient import TestClient

from hext_stream.api.server import create_app
from hext_stream.backend.inprocess_backend import InProcessBackend
from hext_stream.runtime.adapter import EventBusAdapter
from hext_stream.runtime.stream_runtime import HEXTStream, StreamRuntime
from hext_stream.schema.base import HextObject
from hext_stream.schema.replay import ReplayMode, ReplayRequest


@pytest.fixture
def runtime():
    backend = InProcessBackend()
    rt = StreamRuntime(backend=backend, config={"backend": "inprocess", "topics": ["Observation", "Trajectory", "Replay"]})
    yield rt
    rt.close()


def test_hext_stream_publish_subscribe(runtime):
    stream = HEXTStream(runtime)
    seen: list[HextObject] = []
    stream.subscribe("Observation", seen.append)
    stream.publish("Observation", HextObject(source="s", type="observation", payload={"a": 1}))
    time.sleep(0.05)
    assert len(seen) == 1


def test_replay_from_id(runtime):
    ids = []
    for i in range(3):
        ids.append(runtime.publish("Trajectory", HextObject(source="s", type="trajectory", payload={"n": i})))
    events = runtime.replay(ReplayRequest(topic="Trajectory", mode=ReplayMode.LAST_N, last_n=2))
    assert len(events) == 2


def test_event_bus_adapter_migration(runtime):
    adapter = EventBusAdapter(topic="Observation", stream=HEXTStream(runtime))
    adapter.put({"sensor": "imu", "value": 42})
    item = adapter.get(timeout=2.0)
    assert item["payload"]["value"]["sensor"] == "imu"
    adapter.close()


def test_api_health_and_publish(runtime):
    app = create_app(runtime=runtime)
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    resp = client.post(
        "/publish/Observation",
        json={
            "source": "api-test",
            "type": "observation",
            "payload": {"sequence": 1},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"

    hist = client.get("/history/Observation?limit=10")
    assert hist.status_code == 200
    assert hist.json()["count"] >= 1
