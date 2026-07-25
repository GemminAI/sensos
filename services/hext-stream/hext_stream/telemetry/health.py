"""RFC-HEXT014 §6: Runtime Health Monitor.

Every value in the snapshot is read, at query time, from the one place
that already owns it (the Kernel Context, or an adapter reached through
it) — this module stores nothing and computes nothing beyond assembly.
"""

from __future__ import annotations

import resource
from typing import Any

from hext_stream.kernel.context import KernelContext


class RuntimeHealthMonitor:
    """RFC-HEXT014 §6: read-only health snapshot, sourced entirely from
    the Kernel Context (§6 Rules 1-4)."""

    def __init__(self, context: KernelContext) -> None:
        self._context = context

    def snapshot(self) -> dict[str, Any]:
        streams = self._context.streams()
        runtime_health = self._context.health()
        backend_health = runtime_health.get("backend", {})
        redis_status = backend_health if backend_health.get("backend") == "redis" else None

        return {
            # §6 Rule 1
            "kernel_state": self._context.state.value,
            "scheduler_state": {
                "kernel_state": self._context.state.value,
                "streams_admitted": {s: self._context.last_sequence(s) for s in streams},
            },
            "processor_count": len(self._context.processors()),
            # §6 Rule 2
            "stream_count": len(streams),
            "stream_lifecycle": {s: self._as_value(self._context.stream_lifecycle(s)) for s in streams},
            # §6 Rule 3
            "queue_length": {s: self._context.queue_length(s) for s in streams},
            "redis_status": redis_status,
            # §6 Rule 4 — platform-dependent unit (KB on Linux, bytes on
            # macOS); reported as-is, not normalized, since no other
            # component in this family tracks process memory to compare
            # against or a unit convention to match.
            "memory_usage_ru_maxrss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }

    @staticmethod
    def _as_value(state: Any) -> str | None:
        return state.value if state is not None else None
