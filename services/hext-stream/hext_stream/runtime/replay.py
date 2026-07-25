"""Deterministic replay engine."""

from __future__ import annotations

import time
from datetime import datetime

from hext_stream.backend.backend_interface import StreamBackend
from hext_stream.runtime.metrics import MetricsCollector
from hext_stream.schema.base import HextObject
from hext_stream.schema.replay import ReplayMode, ReplayRequest


class ReplayEngine:
    """Ordered replay preserving lineage and causality."""

    def __init__(self, backend: StreamBackend, metrics: MetricsCollector) -> None:
        self._backend = backend
        self._metrics = metrics

    def replay(self, request: ReplayRequest) -> list[HextObject]:
        start = time.perf_counter()
        if request.mode == ReplayMode.FROM_ID:
            events = self._backend.replay(request.topic, from_id=request.from_id)
        elif request.mode == ReplayMode.FROM_TIMESTAMP:
            events = self._backend.replay(
                request.topic, from_timestamp=request.from_timestamp
            )
        else:
            events = self._backend.replay(request.topic, last_n=request.last_n)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        self._metrics.record_replay(elapsed_ms)
        return events

    def replay_from_timestamp(
        self, topic: str, from_timestamp: datetime
    ) -> list[HextObject]:
        return self.replay(
            ReplayRequest(
                topic=topic,
                mode=ReplayMode.FROM_TIMESTAMP,
                from_timestamp=from_timestamp,
            )
        )

    def replay_from_id(self, topic: str, from_id: str) -> list[HextObject]:
        return self.replay(
            ReplayRequest(topic=topic, mode=ReplayMode.FROM_ID, from_id=from_id)
        )

    def replay_last_n(self, topic: str, n: int) -> list[HextObject]:
        return self.replay(
            ReplayRequest(topic=topic, mode=ReplayMode.LAST_N, last_n=n)
        )
