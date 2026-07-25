"""HEXT STREAM runtime orchestrator."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from hext_stream.backend.backend_interface import Callback, StreamBackend, SubscriptionHandle
from hext_stream.backend.inprocess_backend import InProcessBackend
from hext_stream.backend.redis_backend import RedisBackend
from hext_stream.observation.allocators import SequenceAllocator, compute_payload_digest
from hext_stream.runtime.consumer import ConsumerManager
from hext_stream.runtime.history import HistoryService
from hext_stream.runtime.metrics import MetricsCollector
from hext_stream.runtime.replay import ReplayEngine
from hext_stream.runtime.router import TopicRouter
from hext_stream.schema.base import HextObject
from hext_stream.schema.replay import ReplayRequest


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or os.environ.get("HEXT_STREAM_CONFIG", "hext_stream/config/stream.yaml"))
    if not config_path.exists():
        return {
            "backend": os.environ.get("HEXT_STREAM_BACKEND", "inprocess"),
            "redis_url": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            "topics": list(TopicRouter().topics),
            "history_days": 30,
        }
    with config_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def create_backend(config: dict[str, Any]) -> StreamBackend:
    backend_name = (config.get("backend") or "inprocess").lower()
    if backend_name == "redis":
        return RedisBackend(url=config.get("redis_url", "redis://localhost:6379/0"))
    return InProcessBackend()


class StreamRuntime:
    """Production runtime wiring backend, router, replay, history, and metrics."""

    def __init__(
        self,
        *,
        backend: StreamBackend | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.config = config or load_config()
        self.backend = backend or create_backend(self.config)
        self.metrics = MetricsCollector()
        self.router = TopicRouter(self.config.get("topics"))
        self.consumers = ConsumerManager(self.backend, self.metrics)
        self.replay_engine = ReplayEngine(self.backend, self.metrics)
        self.history_service = HistoryService(self.backend, self.metrics)
        # RFC-HEXT013 §5.2/§6: one shared, per-runtime allocator so sequence
        # numbers stay monotonic per topic regardless of which caller
        # (Observation Driver, Processor Pipeline, or a direct publish())
        # originated the object.
        self.sequence_allocator = SequenceAllocator()
        health = self.backend.health()
        self.metrics.set_backend_status(health.get("status", "unknown"))

    def publish(self, topic: str, obj: HextObject) -> str:
        topic, obj = self.router.route(topic, obj)
        # RFC-HEXT013 §5.2/§6: additive metadata only — never touches id,
        # timestamp, payload, or any existing metadata key, so this is safe
        # for objects that already carry caller-assigned identity (e.g. CTS
        # fixtures) as well as freshly ingested ones.
        stamped_metadata = dict(obj.metadata)
        stamped_metadata["sequence"] = self.sequence_allocator.allocate(topic)
        stamped_metadata["payload_digest"] = compute_payload_digest(obj.payload)
        obj = obj.model_copy(update={"metadata": stamped_metadata})
        start = time.perf_counter()
        event_id = self.backend.publish(topic, obj)
        self.metrics.record_publish((time.perf_counter() - start) * 1000.0, topic)
        self.metrics.set_queue_depth(topic, self.backend.queue_depth(topic))
        return event_id

    def subscribe(
        self,
        topic: str,
        callback: Callback,
        *,
        last_id: str = "$",
    ) -> SubscriptionHandle:
        self.router.validate(topic)
        return self.consumers.subscribe(topic, callback, last_id=last_id)

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        self.consumers.unsubscribe(handle)

    def replay(self, request: ReplayRequest) -> list[HextObject]:
        self.router.validate(request.topic)
        return self.replay_engine.replay(request)

    def history(self, topic: str, *, limit: int = 100) -> list[HextObject]:
        self.router.validate(topic)
        return self.history_service.fetch(topic, limit=limit)

    def health(self) -> dict[str, Any]:
        backend_health = self.backend.health()
        return {
            "status": backend_health.get("status", "unknown"),
            "backend": backend_health,
            "topics": self.router.topics,
            "active_subscriptions": len(self.consumers.active_subscriptions()),
        }

    def metrics_dict(self) -> dict[str, Any]:
        return self.metrics.to_dict()

    def close(self) -> None:
        for handle in list(self.consumers.active_subscriptions()):
            self.consumers.unsubscribe(handle)
        self.backend.close()


class HEXTStream:
    """
    Public ABI facade.

    All SensOS components communicate through publish() / subscribe() only.
    """

    _instance: StreamRuntime | None = None

    def __init__(self, runtime: StreamRuntime | None = None) -> None:
        self._runtime = runtime or HEXTStream.get_runtime()

    @classmethod
    def get_runtime(cls) -> StreamRuntime:
        if cls._instance is None:
            cls._instance = StreamRuntime()
        return cls._instance

    @classmethod
    def configure(cls, *, backend: StreamBackend | None = None, config: dict[str, Any] | None = None) -> StreamRuntime:
        if cls._instance is not None:
            cls._instance.close()
        cls._instance = StreamRuntime(backend=backend, config=config)
        return cls._instance

    def publish(self, topic: str, obj: HextObject) -> str:
        return self._runtime.publish(topic, obj)

    def subscribe(self, topic: str, callback: Callable[[HextObject], None], *, last_id: str = "$") -> SubscriptionHandle:
        return self._runtime.subscribe(topic, callback, last_id=last_id)

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        self._runtime.unsubscribe(handle)

    def replay(self, request: ReplayRequest) -> list[HextObject]:
        return self._runtime.replay(request)

    def history(self, topic: str, *, limit: int = 100) -> list[HextObject]:
        return self._runtime.history(topic, limit=limit)

    def health(self) -> dict[str, Any]:
        return self._runtime.health()

    def metrics(self) -> dict[str, Any]:
        return self._runtime.metrics_dict()
