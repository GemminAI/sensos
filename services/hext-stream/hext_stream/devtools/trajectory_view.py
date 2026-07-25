"""RFC-HEXT008 (Task 10): DevTools <-> TrajectoryManager integration.

Displays current trajectory, replay position, branch id, and snapshot id
— all sourced from `KernelContext.trajectory_manager` (a reference, per
[RFC-HEXT015] §5.2), never independently tracked by DevTools.
"""

from __future__ import annotations

from typing import Any

from hext_stream.kernel.context import KernelContext


class TrajectoryView:
    """RFC-HEXT008 Task 10: a direct presentation of
    `TrajectoryManager.session_view()` — computes and stores nothing of
    its own, mirroring `RuntimeStateViewer`'s relationship to the Runtime
    Health Monitor (§3.4)."""

    def __init__(self, context: KernelContext) -> None:
        self._context = context

    def view(self) -> dict[str, Any]:
        return self._context.trajectory_manager.session_view()
