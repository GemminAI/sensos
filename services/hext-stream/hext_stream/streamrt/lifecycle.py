"""RFC-HEXT012 §4: Stream Lifecycle.

Created -> Connected -> Active <-> Paused -> Closed, per stream (topic),
independent of and finer-grained than the Execution Kernel's own
BOOT/LOAD/READY/RUNNING/PAUSED/SHUTDOWN state machine (RFC-HEXT011 §2).
"""

from __future__ import annotations

import threading
from enum import Enum


class StreamLifecycleState(str, Enum):
    CREATED = "Created"
    CONNECTED = "Connected"
    ACTIVE = "Active"
    PAUSED = "Paused"
    CLOSED = "Closed"


class StreamLifecycleError(Exception):
    """Raised on a transition not permitted by RFC-HEXT012 §4.2."""


_ALLOWED: dict[StreamLifecycleState, frozenset[StreamLifecycleState]] = {
    StreamLifecycleState.CREATED: frozenset({StreamLifecycleState.CONNECTED}),
    StreamLifecycleState.CONNECTED: frozenset({StreamLifecycleState.ACTIVE}),
    StreamLifecycleState.ACTIVE: frozenset({StreamLifecycleState.PAUSED, StreamLifecycleState.CLOSED}),
    StreamLifecycleState.PAUSED: frozenset({StreamLifecycleState.ACTIVE, StreamLifecycleState.CLOSED}),
    StreamLifecycleState.CLOSED: frozenset(),
}


class StreamLifecycleManager:
    """RFC-HEXT012 §4: per-topic lifecycle state, the single source of
    truth exposed through the Kernel Context (§4.3)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, StreamLifecycleState] = {}

    def create(self, topic: str) -> StreamLifecycleState:
        """§4.1 Rule 1: register a topic as Created. Idempotent — creating
        an already-known topic returns its current state unchanged."""
        with self._lock:
            if topic not in self._states:
                self._states[topic] = StreamLifecycleState.CREATED
            return self._states[topic]

    def transition(self, topic: str, target: StreamLifecycleState) -> StreamLifecycleState:
        with self._lock:
            current = self._states.get(topic)
            if current is None:
                raise StreamLifecycleError(f"stream {topic!r} was never Created")
            allowed = _ALLOWED[current]
            if target not in allowed:
                raise StreamLifecycleError(
                    f"RFC-HEXT012 §4.2: {current.value} -> {target.value} "
                    f"is not a permitted transition for stream {topic!r} "
                    f"(allowed: {sorted(s.value for s in allowed)})"
                )
            self._states[topic] = target
            return target

    def state(self, topic: str) -> StreamLifecycleState | None:
        with self._lock:
            return self._states.get(topic)

    def streams(self) -> list[str]:
        with self._lock:
            return list(self._states.keys())
