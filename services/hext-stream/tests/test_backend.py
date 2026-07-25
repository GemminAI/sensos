"""Backend interface tests."""

import threading
import time

from hext_stream.backend.inprocess_backend import InProcessBackend
from hext_stream.schema.base import HextObject


def test_publish_subscribe_roundtrip():
    backend = InProcessBackend()
    received: list[HextObject] = []
    event = threading.Event()

    def on_event(obj: HextObject) -> None:
        received.append(obj)
        event.set()

    backend.subscribe("Observation", on_event)
    obj = HextObject(source="test", type="observation", payload={"x": 1})
    backend.publish("Observation", obj)
    assert event.wait(timeout=2.0)
    assert received[0].payload["x"] == 1
    backend.close()


def test_replay_last_n_preserves_order():
    backend = InProcessBackend()
    for i in range(5):
        backend.publish(
            "Trajectory",
            HextObject(source="t", type="trajectory", payload={"i": i}),
        )
    replayed = backend.replay("Trajectory", last_n=3)
    assert [e.payload["i"] for e in replayed] == [2, 3, 4]
    backend.close()


def test_history_limit():
    backend = InProcessBackend()
    for i in range(10):
        backend.publish(
            "Diagnostic",
            HextObject(source="d", type="diagnostic", payload={"i": i}),
        )
    history = backend.history("Diagnostic", limit=4)
    assert len(history) == 4
    assert history[-1].payload["i"] == 9
    backend.close()


def test_health_ok():
    backend = InProcessBackend()
    assert backend.health()["status"] == "ok"
    backend.close()
