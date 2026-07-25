"""RFC-HEXT011 §2: Execution State Machine.

BOOT -> LOAD -> READY -> RUNNING <-> PAUSED -> SHUTDOWN, where BOOT/LOAD/
READY are macro-states over RFC-HEXT010 §3's ten boot states (READY is an
alias of RFC-HEXT010's RUNTIME_READY, not a new state) and RUNNING/PAUSED/
SHUTDOWN are new to RFC-HEXT011 §2.1.
"""

from __future__ import annotations

import threading
from enum import Enum
from typing import Callable


class KernelState(str, Enum):
    BOOT = "BOOT"
    LOAD = "LOAD"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SHUTDOWN = "SHUTDOWN"


class KernelTransitionError(Exception):
    """Raised on a transition not permitted by RFC-HEXT011 §2.2."""


# RFC-HEXT011 §2.2: the only transitions a conformant kernel may perform.
_ALLOWED: dict[KernelState, frozenset[KernelState]] = {
    KernelState.BOOT: frozenset({KernelState.LOAD}),
    KernelState.LOAD: frozenset({KernelState.READY}),
    KernelState.READY: frozenset({KernelState.RUNNING}),
    KernelState.RUNNING: frozenset({KernelState.PAUSED, KernelState.SHUTDOWN}),
    KernelState.PAUSED: frozenset({KernelState.RUNNING, KernelState.SHUTDOWN}),
    KernelState.SHUTDOWN: frozenset(),
}


class KernelStateMachine:
    """RFC-HEXT011 §2: enforces the fixed macro-state transition graph."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = KernelState.BOOT
        self._history: list[KernelState] = [KernelState.BOOT]
        # Additive, Phase 2 hook: optional observers notified after a
        # successful transition, e.g. so Telemetry Runtime ([RFC-HEXT014]
        # §3.6) can emit `runtime.state` without this class needing to
        # know Telemetry Runtime exists. Registering zero listeners (the
        # Phase 1 default) leaves every existing behavior unchanged.
        self._listeners: list[Callable[[KernelState, KernelState], None]] = []

    @property
    def state(self) -> KernelState:
        with self._lock:
            return self._state

    @property
    def history(self) -> list[KernelState]:
        with self._lock:
            return list(self._history)

    def add_listener(self, listener: Callable[[KernelState, KernelState], None]) -> None:
        """Register a callback invoked ``(previous, new)`` after each
        successful transition. Additive-only — does not affect transition
        validation or any existing caller that does not use this."""
        with self._lock:
            self._listeners.append(listener)

    def transition(self, target: KernelState) -> KernelState:
        with self._lock:
            allowed = _ALLOWED[self._state]
            if target not in allowed:
                raise KernelTransitionError(
                    f"RFC-HEXT011 §2.2: {self._state.value} -> {target.value} "
                    f"is not a permitted transition (allowed: "
                    f"{sorted(s.value for s in allowed)})"
                )
            previous = self._state
            self._state = target
            self._history.append(target)
            listeners = list(self._listeners)
        # Invoked outside the lock so a listener reading .state cannot deadlock.
        for listener in listeners:
            listener(previous, target)
        return target
