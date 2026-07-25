"""RFC-HEXT015 §2 (Task 6): Snapshot Manager.

Snapshots reference existing `HextObject`s (the same instances
`history()` already hands out, per [RFC-HEXT012] §5's zero-copy
discipline) — never duplicating an Observation's payload. Implemented
atop the existing `history()` read path ([RFC-HEXT015] §2 Rule 4);
no parallel storage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from hext_stream.kernel.context import KernelContext
from hext_stream.schema.base import HextObject

HistoryFn = Callable[..., list[HextObject]]

_HISTORY_SCAN_LIMIT = 100_000


class SnapshotHandle:
    """RFC-HEXT015 §2 Rule 2: read-only, reference-only view."""

    def __init__(self, *, stream: str, objects: list[HextObject], sequence_bound: int | None) -> None:
        self._stream = stream
        self._objects = objects  # same HextObject references history() returned
        self._sequence_bound = sequence_bound

    @property
    def stream(self) -> str:
        return self._stream

    def objects(self) -> list[HextObject]:
        """Returns a new list, but every element is the identical
        `HextObject` reference `history()` produced — no payload copy."""
        return list(self._objects)

    def sequence_bound(self) -> int | None:
        return self._sequence_bound


class SnapshotManager:
    """RFC-HEXT015 §2 / Task 6."""

    def __init__(self, *, history_fn: HistoryFn, context: KernelContext) -> None:
        self._history_fn = history_fn
        self._context = context

    def at_sequence(self, stream: str, sequence: int) -> SnapshotHandle:
        """RFC-HEXT015 §2 Rule 1: addressable by `metadata.sequence`."""
        objects = [
            o for o in self._history_fn(stream, limit=_HISTORY_SCAN_LIMIT)
            if (s := o.metadata.get("sequence")) is not None and s <= sequence
        ]
        objects.sort(key=lambda o: o.metadata.get("sequence", 0))
        bound = objects[-1].metadata.get("sequence") if objects else None
        return SnapshotHandle(stream=stream, objects=objects, sequence_bound=bound)

    def at_timestamp(self, stream: str, timestamp: datetime) -> SnapshotHandle:
        objects = [o for o in self._history_fn(stream, limit=_HISTORY_SCAN_LIMIT) if o.timestamp <= timestamp]
        objects.sort(key=lambda o: o.metadata.get("sequence", 0))
        bound = objects[-1].metadata.get("sequence") if objects else None
        return SnapshotHandle(stream=stream, objects=objects, sequence_bound=bound)

    def current_sequence_bound(self, stream: str) -> int | None:
        """RFC-HEXT015 §2 Rule 3: sourced from the Kernel Context, not a
        second, independently tracked counter."""
        return self._context.last_sequence(stream)
