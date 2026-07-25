"""CTS runtime session — real runtime only, no mocks."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi.testclient import TestClient

from hext_stream.api.server import create_app
from hext_stream.backend.backend_interface import StreamBackend
from hext_stream.backend.inprocess_backend import InProcessBackend
from hext_stream.backend.redis_backend import RedisBackend
from hext_stream.runtime.stream_runtime import StreamRuntime
from hext_stream.schema.base import HextObject, utcnow
from hext_stream.schema.replay import ReplayMode, ReplayRequest


REQUIRED_TOPICS = {
    "Observation",
    "Trajectory",
    "TrajectoryFlow",
    "Replay",
    "Controller",
    "Reality",
    "Diagnostic",
    "Metrics",
}


def canonical_json(obj: HextObject | dict[str, Any]) -> bytes:
    data = obj.to_envelope() if isinstance(obj, HextObject) else obj
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass
class PublishResult:
    event_id: str
    object_id: str
    latency_ms: float


@dataclass
class SessionMetrics:
    publish_latencies_ms: list[float] = field(default_factory=list)
    subscribe_latencies_ms: list[float] = field(default_factory=list)
    replay_latencies_ms: list[float] = field(default_factory=list)
    history_latencies_ms: list[float] = field(default_factory=list)


class RuntimeSession:
    """Unified access to a live HEXT STREAM runtime (direct ABI + HTTP)."""

    def __init__(
        self,
        *,
        backend_name: str,
        backend: StreamBackend | None = None,
        redis_url: str = "redis://localhost:6379/0",
        http_base: str | None = None,
    ) -> None:
        self.backend_name = backend_name
        self.started_at = time.monotonic()
        self.session_metrics = SessionMetrics()
        self._event_ids: dict[str, list[str]] = {}

        if backend_name == "http":
            self._mode = "http"
            self._http = httpx.Client(base_url=http_base or "http://localhost:8030", timeout=60.0)
            self.runtime = None
            self._client = None
        else:
            self._mode = "direct"
            self._http = None
            if backend is None:
                backend = (
                    RedisBackend(url=redis_url)
                    if backend_name == "redis"
                    else InProcessBackend()
                )
            self.runtime = StreamRuntime(
                backend=backend,
                config={"backend": backend_name, "topics": sorted(REQUIRED_TOPICS)},
            )
            self._client = TestClient(create_app(runtime=self.runtime))

    def close(self) -> None:
        if self._http:
            self._http.close()
        if self.runtime:
            self.runtime.close()

    def uptime_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def health(self) -> dict[str, Any]:
        if self._mode == "http":
            r = self._http.get("/health")
            r.raise_for_status()
            return r.json()
        r = self._client.get("/health")
        return r.json()

    def topics(self) -> list[str]:
        if self._mode == "http":
            return self._http.get("/topics").json()["topics"]
        return self._client.get("/topics").json()["topics"]

    def metrics(self) -> dict[str, Any]:
        if self._mode == "http":
            return self._http.get("/metrics").json()
        return self._client.get("/metrics").json()

    def publish(self, topic: str, obj: HextObject) -> PublishResult:
        start = time.perf_counter()
        if self._mode == "http":
            body = {
                "source": obj.source,
                "type": obj.type,
                "version": obj.version,
                "payload": obj.payload,
                "metadata": obj.metadata,
                "id": obj.id,
                "timestamp": obj.timestamp.isoformat(),
            }
            r = self._http.post(f"/publish/{topic}", json=body)
            r.raise_for_status()
            data = r.json()
            event_id = data["event_id"]
            object_id = data["object_id"]
        else:
            event_id = self.runtime.publish(topic, obj)
            object_id = obj.id
        latency_ms = (time.perf_counter() - start) * 1000.0
        self.session_metrics.publish_latencies_ms.append(latency_ms)
        self._event_ids.setdefault(topic, []).append(event_id)
        return PublishResult(event_id=event_id, object_id=object_id, latency_ms=latency_ms)

    def subscribe(self, topic: str, callback) -> Any:
        if self._mode == "http":
            raise RuntimeError("Concurrent HTTP SSE subscribe not used in CTS; use direct ABI")
        return self.runtime.subscribe(topic, callback)

    def unsubscribe(self, handle) -> None:
        if self.runtime:
            self.runtime.unsubscribe(handle)

    def replay(
        self,
        topic: str,
        *,
        mode: ReplayMode = ReplayMode.LAST_N,
        from_id: str | None = None,
        from_timestamp: datetime | None = None,
        last_n: int = 100,
    ) -> list[HextObject]:
        start = time.perf_counter()
        if self._mode == "http":
            params: dict[str, Any] = {"mode": mode.value, "last_n": last_n}
            if from_id:
                params["from_id"] = from_id
            if from_timestamp:
                params["from_timestamp"] = from_timestamp.isoformat()
            r = self._http.get(f"/replay/{topic}", params=params)
            r.raise_for_status()
            events = [HextObject.from_envelope(e) for e in r.json()["events"]]
        else:
            events = self.runtime.replay(
                ReplayRequest(
                    topic=topic,
                    mode=mode,
                    from_id=from_id,
                    from_timestamp=from_timestamp,
                    last_n=last_n,
                )
            )
        self.session_metrics.replay_latencies_ms.append((time.perf_counter() - start) * 1000.0)
        return events

    def history(self, topic: str, *, limit: int = 10_000) -> list[HextObject]:
        start = time.perf_counter()
        if self._mode == "http":
            r = self._http.get(f"/history/{topic}", params={"limit": limit})
            r.raise_for_status()
            events = [HextObject.from_envelope(e) for e in r.json()["events"]]
        else:
            events = self.runtime.history(topic, limit=limit)
        self.session_metrics.history_latencies_ms.append((time.perf_counter() - start) * 1000.0)
        return events

    def queue_depth(self, topic: str) -> int:
        if self.runtime:
            return self.runtime.backend.queue_depth(topic)
        # HTTP: infer from metrics topics map if available
        m = self.metrics_endpoint_raw()
        return int(m.get("topics", {}).get(topic, 0))

    def metrics_endpoint_raw(self) -> dict[str, Any]:
        return self.metrics()

    @staticmethod
    def observation(seq: int, *, session: str = "cts") -> HextObject:
        ts = utcnow() + timedelta(microseconds=seq)
        return HextObject(
            id=f"hext:cts-obs-{seq:06d}",
            timestamp=ts,
            source="cts",
            type="observation",
            version="1.0.0",
            payload={"sequence": seq, "curvature": 0.1 * seq},
            metadata={"session": session},
        )
