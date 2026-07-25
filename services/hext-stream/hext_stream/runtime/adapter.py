"""Migration adapter — queue.Queue / EventBus compatibility."""

from __future__ import annotations

import queue
import threading
from typing import Any

from hext_stream.runtime.stream_runtime import HEXTStream
from hext_stream.schema.base import HextObject


class EventBusAdapter:
    """
    Drop-in migration path for legacy queue.Queue() event buses.

    Before:
        bus = queue.Queue()
        bus.put(event_dict)

    After (one-line change):
        bus = EventBusAdapter(topic="Observation")
        bus.put(event_dict)
    """

    def __init__(
        self,
        *,
        topic: str = "Observation",
        stream: HEXTStream | None = None,
        source: str = "legacy-eventbus",
        maxsize: int = 0,
    ) -> None:
        self._stream = stream or HEXTStream()
        self._topic = topic
        self._source = source
        self._local: queue.Queue[Any] = queue.Queue(maxsize=maxsize)
        self._handle = self._stream.subscribe(topic, self._on_event)

    def _on_event(self, obj: HextObject) -> None:
        self._local.put(obj.to_envelope())

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> None:
        if isinstance(item, HextObject):
            obj = item
        elif isinstance(item, dict) and "id" in item and "payload" in item:
            obj = HextObject.from_envelope(item)
        else:
            obj = HextObject(
                source=self._source,
                type="legacy",
                payload={"value": item},
                metadata={"migrated_from": "queue.Queue"},
            )
        self._stream.publish(self._topic, obj)

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        return self._local.get(block=block, timeout=timeout)

    def put_nowait(self, item: Any) -> None:
        self.put(item, block=False)

    def get_nowait(self) -> Any:
        return self.get(block=False)

    def qsize(self) -> int:
        return self._local.qsize()

    def empty(self) -> bool:
        return self._local.empty()

    def close(self) -> None:
        self._stream.unsubscribe(self._handle)


def migrate_event_bus(
    old_bus: queue.Queue[Any],
    *,
    topic: str = "Observation",
    stream: HEXTStream | None = None,
    drain: bool = True,
) -> EventBusAdapter:
    """Drain a legacy queue into HEXT STREAM and return an adapter."""
    adapter = EventBusAdapter(topic=topic, stream=stream)
    if drain:
        while not old_bus.empty():
            try:
                adapter.put(old_bus.get_nowait())
            except queue.Empty:
                break
    return adapter
