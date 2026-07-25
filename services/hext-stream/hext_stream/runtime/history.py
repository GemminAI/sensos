"""Topic history access."""

from __future__ import annotations

from hext_stream.backend.backend_interface import StreamBackend
from hext_stream.runtime.metrics import MetricsCollector
from hext_stream.schema.base import HextObject


class HistoryService:
    """Read-only history facade."""

    def __init__(self, backend: StreamBackend, metrics: MetricsCollector) -> None:
        self._backend = backend
        self._metrics = metrics

    def fetch(self, topic: str, *, limit: int = 100) -> list[HextObject]:
        events = self._backend.history(topic, limit=limit)
        self._metrics.set_queue_depth(topic, self._backend.queue_depth(topic))
        return events
