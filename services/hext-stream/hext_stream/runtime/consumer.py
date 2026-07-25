"""Consumer registry and lifecycle."""

from __future__ import annotations

import time
from typing import Callable

from hext_stream.backend.backend_interface import Callback, StreamBackend, SubscriptionHandle
from hext_stream.runtime.metrics import MetricsCollector
from hext_stream.schema.base import HextObject


class ConsumerManager:
    """Manages topic subscriptions with latency instrumentation."""

    def __init__(self, backend: StreamBackend, metrics: MetricsCollector) -> None:
        self._backend = backend
        self._metrics = metrics
        self._handles: dict[str, SubscriptionHandle] = {}

    def subscribe(
        self,
        topic: str,
        callback: Callback,
        *,
        last_id: str = "$",
    ) -> SubscriptionHandle:
        def _wrapped(obj: HextObject) -> None:
            start = time.perf_counter()
            callback(obj)
            self._metrics.record_consume((time.perf_counter() - start) * 1000.0)

        handle = self._backend.subscribe(topic, _wrapped, last_id=last_id)
        self._handles[handle.subscription_id] = handle
        return handle

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        self._backend.unsubscribe(handle)
        self._handles.pop(handle.subscription_id, None)

    def active_subscriptions(self) -> list[SubscriptionHandle]:
        return [h for h in self._handles.values() if h.active]
