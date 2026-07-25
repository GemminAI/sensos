"""In-process backend for tests and single-process runtimes."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from hext_stream.backend.backend_interface import Callback, StreamBackend, SubscriptionHandle
from hext_stream.schema.base import HextObject


class InProcessBackend(StreamBackend):
    """Thread-safe in-memory stream backend."""

    def __init__(self, *, maxlen: int = 10_000) -> None:
        self._streams: dict[str, deque[tuple[str, HextObject]]] = defaultdict(
            lambda: deque(maxlen=maxlen)
        )
        self._subscriptions: dict[str, tuple[str, Callback]] = {}
        self._lock = threading.RLock()
        self._closed = False

    def publish(self, topic: str, obj: HextObject) -> str:
        with self._lock:
            if self._closed:
                raise RuntimeError("InProcessBackend is closed")
            event_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
            self._streams[topic].append((event_id, obj))
            callbacks = [
                cb for sid, (t, cb) in self._subscriptions.items() if t == topic and sid
            ]
        for callback in callbacks:
            callback(obj)
        return event_id

    def subscribe(
        self,
        topic: str,
        callback: Callback,
        *,
        last_id: str = "$",
    ) -> SubscriptionHandle:
        subscription_id = f"sub-{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._subscriptions[subscription_id] = (topic, callback)
            backlog = list(self._streams.get(topic, []))
        if last_id != "$":
            backlog = [(eid, obj) for eid, obj in backlog if eid >= last_id]
        for _, obj in backlog:
            callback(obj)
        return SubscriptionHandle(subscription_id=subscription_id, topic=topic)

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        with self._lock:
            self._subscriptions.pop(handle.subscription_id, None)
            handle.active = False

    def replay(
        self,
        topic: str,
        *,
        from_id: str | None = None,
        from_timestamp: datetime | None = None,
        last_n: int | None = None,
    ) -> list[HextObject]:
        with self._lock:
            events = list(self._streams.get(topic, []))
        if from_id:
            started = False
            filtered: list[tuple[str, HextObject]] = []
            for eid, obj in events:
                if eid == from_id:
                    started = True
                if started:
                    filtered.append((eid, obj))
            events = filtered if started else []
        if from_timestamp:
            ts = from_timestamp.astimezone(timezone.utc)
            events = [
                (eid, obj)
                for eid, obj in events
                if obj.timestamp.astimezone(timezone.utc) >= ts
            ]
        objects = [obj for _, obj in events]
        if last_n is not None:
            objects = objects[-last_n:]
        return objects

    def history(self, topic: str, *, limit: int = 100) -> list[HextObject]:
        with self._lock:
            events = list(self._streams.get(topic, []))
        return [obj for _, obj in events[-limit:]]

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": "ok" if not self._closed else "closed",
                "backend": "inprocess",
                "topics": len(self._streams),
                "subscriptions": len(self._subscriptions),
            }

    def queue_depth(self, topic: str) -> int:
        with self._lock:
            return len(self._streams.get(topic, []))

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._subscriptions.clear()
