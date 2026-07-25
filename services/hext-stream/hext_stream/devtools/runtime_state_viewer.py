"""RFC-HEXT008 §3.4 (Task 4): Runtime State Viewer.

Sourced exclusively from the Kernel Context. Reuses the existing
`RuntimeHealthMonitor` (RFC-HEXT014 §6, Phase 2) rather than re-reading
`KernelContext` a second, competing way — `RuntimeHealthMonitor` already
assembles exactly Runtime State, Scheduler State, Stream Lifecycle, Queue
Depth, Processor Count, and Health from the Kernel Context alone.
"""

from __future__ import annotations

from typing import Any

from hext_stream.kernel.context import KernelContext
from hext_stream.telemetry.health import RuntimeHealthMonitor


class RuntimeStateViewer:
    """RFC-HEXT008 §3.4 / Task 4: a direct presentation of the Runtime
    Health Monitor snapshot — computes and stores nothing of its own."""

    def __init__(self, context: KernelContext) -> None:
        self._monitor = RuntimeHealthMonitor(context)

    def view(self) -> dict[str, Any]:
        return self._monitor.snapshot()
