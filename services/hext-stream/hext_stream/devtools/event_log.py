"""RFC-HEXT008 (Task 2): Semantic Event Log — append-only viewer over the
telemetry stream, with filter/search. No mutation: this module never calls
anything that could alter a published event, only `TelemetryAPI.event_log`.

Note on "runtime id": no such field is emitted anywhere in this family's
telemetry (RFC-HEXT014 §3 defines no `runtime_id`). Rather than invent one
— forbidden by this phase's "do not invent telemetry the Runtime does not
emit" constraint — this module interprets "runtime id" as `HextObject.source`,
the one existing field that identifies which component produced an event
(e.g. `"telemetry-runtime"`), and filters on that.
"""

from __future__ import annotations

from hext_stream.schema.base import HextObject
from hext_stream.telemetry.api import TelemetryAPI


class EventLog:
    """RFC-HEXT008 Task 2: filter/search over the append-only telemetry
    event log. Every method is read-only over `TelemetryAPI.event_log()`."""

    def __init__(self, telemetry: TelemetryAPI) -> None:
        self._telemetry = telemetry

    def all(self, *, limit: int = 1000) -> list[HextObject]:
        return self._telemetry.event_log(limit=limit)

    def filter(
        self,
        *,
        limit: int = 1000,
        type: str | None = None,
        processor_type: str | None = None,
        trajectory_id: str | None = None,
        runtime_id: str | None = None,
    ) -> list[HextObject]:
        """Filter by event `type`, `payload.processor_type` (present on
        `processor.*` events), `payload.trajectory_id` (present on
        `semantic.metric`/`controller.command` events), or `source`
        (this module's reading of "runtime id" — see module docstring)."""
        events = self._telemetry.event_log(limit=limit)
        if type is not None:
            events = [e for e in events if e.type == type]
        if processor_type is not None:
            events = [e for e in events if e.payload.get("processor_type") == processor_type]
        if trajectory_id is not None:
            events = [e for e in events if e.payload.get("trajectory_id") == trajectory_id]
        if runtime_id is not None:
            events = [e for e in events if e.source == runtime_id]
        return events

    def search(self, query: str, *, limit: int = 1000) -> list[HextObject]:
        """Substring search over each event's `type`, `source`, and the
        string representation of its `payload` values — a simple,
        dependency-free search adequate for an append-only log viewer."""
        needle = query.lower()
        results = []
        for event in self._telemetry.event_log(limit=limit):
            haystack = " ".join(
                [event.type, event.source, *(str(v) for v in event.payload.values())]
            ).lower()
            if needle in haystack:
                results.append(event)
        return results
