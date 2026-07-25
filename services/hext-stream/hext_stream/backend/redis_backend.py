"""Redis Streams backend — first production transport."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from hext_stream.backend.backend_interface import Callback, StreamBackend, SubscriptionHandle
from hext_stream.schema.base import HextObject

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]


def _stream_key(topic: str) -> str:
    return f"hext:stream:{topic}"


class RedisBackend(StreamBackend):
    """Redis Streams implementation hidden behind StreamBackend ABI."""

    def __init__(
        self,
        *,
        url: str = "redis://localhost:6379/0",
        maxlen: int = 100_000,
        block_ms: int = 1000,
    ) -> None:
        if redis is None:
            raise ImportError("redis package required: pip install redis")
        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._maxlen = maxlen
        self._block_ms = block_ms
        self._subscriptions: dict[str, tuple[str, Callback, threading.Event]] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._closed = False

    def publish(self, topic: str, obj: HextObject) -> str:
        key = _stream_key(topic)
        payload = json.dumps(obj.to_envelope())
        event_id = self._client.xadd(key, {"data": payload}, maxlen=self._maxlen, approximate=True)
        return str(event_id)

    def subscribe(
        self,
        topic: str,
        callback: Callback,
        *,
        last_id: str = "$",
    ) -> SubscriptionHandle:
        subscription_id = f"sub-{uuid.uuid4().hex[:12]}"
        stop_event = threading.Event()
        self._subscriptions[subscription_id] = (topic, callback, stop_event)

        def _poll() -> None:
            key = _stream_key(topic)
            cursor = last_id
            while not stop_event.is_set() and not self._closed:
                try:
                    rows = self._client.xread({key: cursor}, block=self._block_ms, count=50)
                except Exception:
                    time.sleep(0.2)
                    continue
                if not rows:
                    continue
                for _, messages in rows:
                    for msg_id, fields in messages:
                        cursor = msg_id
                        raw = fields.get("data")
                        if not raw:
                            continue
                        try:
                            obj = HextObject.from_envelope(json.loads(raw))
                        except Exception:
                            continue
                        callback(obj)

        thread = threading.Thread(target=_poll, name=f"hext-sub-{topic}", daemon=True)
        self._threads[subscription_id] = thread
        thread.start()
        return SubscriptionHandle(subscription_id=subscription_id, topic=topic)

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        entry = self._subscriptions.pop(handle.subscription_id, None)
        if entry:
            _, _, stop_event = entry
            stop_event.set()
        thread = self._threads.pop(handle.subscription_id, None)
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        handle.active = False

    def replay(
        self,
        topic: str,
        *,
        from_id: str | None = None,
        from_timestamp: datetime | None = None,
        last_n: int | None = None,
    ) -> list[HextObject]:
        key = _stream_key(topic)
        start = from_id or "-"
        rows = self._client.xrange(key, min=start, max="+")
        objects: list[HextObject] = []
        for msg_id, fields in rows:
            raw = fields.get("data")
            if not raw:
                continue
            try:
                obj = HextObject.from_envelope(json.loads(raw))
            except Exception:
                continue
            if from_timestamp:
                ts = from_timestamp.astimezone(timezone.utc)
                if obj.timestamp.astimezone(timezone.utc) < ts:
                    continue
            objects.append(obj)
        if last_n is not None:
            objects = objects[-last_n:]
        return objects

    def history(self, topic: str, *, limit: int = 100) -> list[HextObject]:
        key = _stream_key(topic)
        rows = self._client.xrevrange(key, max="+", min="-", count=limit)
        objects: list[HextObject] = []
        for _, fields in reversed(rows):
            raw = fields.get("data")
            if not raw:
                continue
            try:
                objects.append(HextObject.from_envelope(json.loads(raw)))
            except Exception:
                continue
        return objects

    def health(self) -> dict[str, Any]:
        try:
            pong = self._client.ping()
            info = self._client.info("server")
            return {
                "status": "ok" if pong else "degraded",
                "backend": "redis",
                "redis_version": info.get("redis_version", "unknown"),
            }
        except Exception as exc:
            return {"status": "error", "backend": "redis", "error": str(exc)}

    def queue_depth(self, topic: str) -> int:
        try:
            return int(self._client.xlen(_stream_key(topic)))
        except Exception:
            return 0

    def close(self) -> None:
        self._closed = True
        for sid in list(self._subscriptions):
            self.unsubscribe(SubscriptionHandle(subscription_id=sid, topic=""))
        try:
            self._client.close()
        except Exception:
            pass
