"""RFC-HEXT008 §2.1 (Task 1): Processor Trace.

Built entirely from `TelemetryAPI.event_log()` — the `processor.started`/
`processor.completed`/`processor.failed` events RFC-HEXT014 §3.1-3.3
already defines. No Runtime access beyond the Telemetry API; no telemetry
invented (correlation of started/completed pairs, and the dependency
graph, are read-side computations over already-emitted events, not new
emitted state).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hext_stream.telemetry.api import TelemetryAPI

PROCESSOR_EVENT_TYPES = frozenset({"processor.started", "processor.completed", "processor.failed"})


@dataclass(frozen=True)
class ProcessorExecution:
    processor_id: str
    processor_type: str
    input_object_id: str
    output_object_id: str | None
    status: str  # "started" | "completed" | "failed"
    execution_time_ms: float | None
    error_code: str | None
    error_message: str | None
    sequence: int | None
    timestamp: datetime


class ProcessorTrace:
    """RFC-HEXT008 §2.1 / Task 1: execution trace, dependency graph,
    parent/child relationships, and timeline — all read-side views over
    the same `processor.*` telemetry events."""

    def __init__(self, telemetry: TelemetryAPI) -> None:
        self._telemetry = telemetry

    def executions(self, *, limit: int = 1000) -> list[ProcessorExecution]:
        """One entry per `processor.started`/`completed`/`failed` event,
        in publication order (= Runtime Timeline)."""
        out: list[ProcessorExecution] = []
        for event in self._telemetry.event_log(limit=limit):
            if event.type not in PROCESSOR_EVENT_TYPES:
                continue
            p = event.payload
            out.append(
                ProcessorExecution(
                    processor_id=p["processor_id"],
                    processor_type=p["processor_type"],
                    input_object_id=p["input_object_id"],
                    output_object_id=p.get("output_object_id"),
                    status=event.type.removeprefix("processor."),
                    execution_time_ms=p.get("execution_time_ms"),
                    error_code=p.get("error_code"),
                    error_message=p.get("error_message"),
                    sequence=event.metadata.get("sequence"),
                    timestamp=event.timestamp,
                )
            )
        return out

    def timeline(self, *, limit: int = 1000) -> list[ProcessorExecution]:
        """Alias for `executions` — already publication-ordered, which
        for telemetry events is the Runtime Timeline."""
        return self.executions(limit=limit)

    def dependency_graph(self, *, limit: int = 1000) -> dict[str, list]:
        """Parent/child edges: an object is a "child" of whichever object
        was the `input_object_id` of the processor invocation that
        produced it (`output_object_id`). Built from `processor.completed`
        events only — a `processor.failed` invocation produced no output,
        so it contributes no edge."""
        nodes: set[str] = set()
        edges: list[tuple[str, str]] = []
        for execution in self.executions(limit=limit):
            if execution.status != "completed" or execution.output_object_id is None:
                continue
            nodes.add(execution.input_object_id)
            nodes.add(execution.output_object_id)
            edges.append((execution.input_object_id, execution.output_object_id))
        return {"nodes": sorted(nodes), "edges": edges}

    def children_of(self, object_id: str, *, limit: int = 1000) -> list[ProcessorExecution]:
        """Every processor execution that consumed `object_id` as its input."""
        return [e for e in self.executions(limit=limit) if e.input_object_id == object_id]

    def parent_of(self, object_id: str, *, limit: int = 1000) -> ProcessorExecution | None:
        """The processor execution that produced `object_id`, if any."""
        for e in self.executions(limit=limit):
            if e.output_object_id == object_id:
                return e
        return None
