"""Runtime metrics collector."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricsSnapshot:
    publish_latency_ms: float = 0.0
    consumer_latency_ms: float = 0.0
    replay_latency_ms: float = 0.0
    queue_depth: int = 0
    throughput_per_sec: float = 0.0
    publish_count: int = 0
    consume_count: int = 0
    replay_count: int = 0
    backend_status: str = "unknown"
    topics: dict[str, int] = field(default_factory=dict)


class MetricsCollector:
    """Thread-safe runtime metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._publish_latencies: list[float] = []
        self._consumer_latencies: list[float] = []
        self._replay_latencies: list[float] = []
        self._publish_count = 0
        self._consume_count = 0
        self._replay_count = 0
        self._topic_depths: dict[str, int] = {}
        self._backend_status = "unknown"
        self._window_start = time.monotonic()
        self._window_publishes = 0

    def record_publish(self, latency_ms: float, topic: str) -> None:
        with self._lock:
            self._publish_latencies.append(latency_ms)
            self._publish_count += 1
            self._window_publishes += 1
            self._topic_depths[topic] = self._topic_depths.get(topic, 0) + 1

    def record_consume(self, latency_ms: float) -> None:
        with self._lock:
            self._consumer_latencies.append(latency_ms)
            self._consume_count += 1

    def record_replay(self, latency_ms: float) -> None:
        with self._lock:
            self._replay_latencies.append(latency_ms)
            self._replay_count += 1

    def set_queue_depth(self, topic: str, depth: int) -> None:
        with self._lock:
            self._topic_depths[topic] = depth

    def set_backend_status(self, status: str) -> None:
        with self._lock:
            self._backend_status = status

    def _avg(self, values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            elapsed = max(time.monotonic() - self._window_start, 0.001)
            throughput = self._window_publishes / elapsed
            total_depth = sum(self._topic_depths.values())
            return MetricsSnapshot(
                publish_latency_ms=self._avg(self._publish_latencies[-1000:]),
                consumer_latency_ms=self._avg(self._consumer_latencies[-1000:]),
                replay_latency_ms=self._avg(self._replay_latencies[-1000:]),
                queue_depth=total_depth,
                throughput_per_sec=throughput,
                publish_count=self._publish_count,
                consume_count=self._consume_count,
                replay_count=self._replay_count,
                backend_status=self._backend_status,
                topics=dict(self._topic_depths),
            )

    def to_dict(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {
            "publish_latency_ms": round(snap.publish_latency_ms, 4),
            "consumer_latency_ms": round(snap.consumer_latency_ms, 4),
            "replay_latency_ms": round(snap.replay_latency_ms, 4),
            "queue_depth": snap.queue_depth,
            "throughput_per_sec": round(snap.throughput_per_sec, 4),
            "publish_count": snap.publish_count,
            "consume_count": snap.consume_count,
            "replay_count": snap.replay_count,
            "backend_status": snap.backend_status,
            "topics": snap.topics,
        }
