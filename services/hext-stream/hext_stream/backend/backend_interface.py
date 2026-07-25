"""Abstract stream backend — all transports implement this ABI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from hext_stream.schema.base import HextObject

Callback = Callable[[HextObject], None]


@dataclass
class SubscriptionHandle:
    """Opaque subscription reference returned by subscribe()."""

    subscription_id: str
    topic: str
    active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class StreamBackend(ABC):
    """
    Backend-agnostic HEXT STREAM transport interface.

    Higher-level code MUST NOT call Redis/Kafka/NATS APIs directly.
    """

    @abstractmethod
    def publish(self, topic: str, obj: HextObject) -> str:
        """Publish a HextObject. Returns backend event id."""

    @abstractmethod
    def subscribe(
        self,
        topic: str,
        callback: Callback,
        *,
        last_id: str = "$",
    ) -> SubscriptionHandle:
        """Register a callback for topic events."""

    @abstractmethod
    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        """Stop a subscription."""

    @abstractmethod
    def replay(
        self,
        topic: str,
        *,
        from_id: str | None = None,
        from_timestamp: datetime | None = None,
        last_n: int | None = None,
    ) -> list[HextObject]:
        """Deterministic ordered replay."""

    @abstractmethod
    def history(self, topic: str, *, limit: int = 100) -> list[HextObject]:
        """Return recent events for a topic."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Backend health status."""

    @abstractmethod
    def queue_depth(self, topic: str) -> int:
        """Approximate pending/retained event count."""

    @abstractmethod
    def close(self) -> None:
        """Release backend resources."""
