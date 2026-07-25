"""RFC-HEXT014: Telemetry Runtime — composes emission, aggregation, and
health reporting over the Kernel Context, per [RFC-HEXT011] §6.4's
"exactly one instance per subsystem need" pattern.
"""

from __future__ import annotations

from typing import Callable

from hext_stream.kernel.context import KernelContext
from hext_stream.kernel.state_machine import KernelStateMachine
from hext_stream.processors.registry import ProcessorRegistry
from hext_stream.schema.base import HextObject
from hext_stream.telemetry.aggregator import MetricAggregator
from hext_stream.telemetry.emitter import KernelStateTelemetry, ProcessorTelemetry, PublishFn
from hext_stream.telemetry.health import RuntimeHealthMonitor

HistoryFn = Callable[..., list[HextObject]]


class TelemetryRuntime:
    """RFC-HEXT014: the producer side. See ``telemetry.api.TelemetryAPI``
    for the read-only surface consumers (§8) should use instead of this
    class directly.
    """

    def __init__(
        self,
        *,
        registry: ProcessorRegistry,
        state_machine: KernelStateMachine,
        context: KernelContext,
        publish_fn: PublishFn,
        history_fn: HistoryFn,
        telemetry_topic: str = "Telemetry",
        source: str = "telemetry-runtime",
    ) -> None:
        self.processor_telemetry = ProcessorTelemetry(
            registry, publish_fn, telemetry_topic=telemetry_topic, source=source
        )
        self.state_telemetry = KernelStateTelemetry(
            state_machine, publish_fn, telemetry_topic=telemetry_topic, source=source
        )
        self.aggregator = MetricAggregator()
        self.health_monitor = RuntimeHealthMonitor(context)
        # DevTools (RFC-HEXT008 Tasks 1-2) needs read access to the raw
        # telemetry event log, not only the aggregated metric series.
        # Injected as a callable (StreamRuntime.history, in practice) so
        # this class — and everything built on it, including
        # TelemetryAPI — never needs a StreamRuntime/ExecutionKernel
        # reference of its own.
        self._history_fn = history_fn
        self._topic = telemetry_topic

    def event_log(self, *, limit: int = 1000) -> list[HextObject]:
        """RFC-HEXT008 §2.1/Task 2: the raw, append-only telemetry event
        history, in publication (= `metadata.sequence`) order."""
        return self._history_fn(self._topic, limit=limit)

    def dispatch_and_emit(self, event: HextObject) -> list[HextObject]:
        """RFC-HEXT014 §3.1-3.3 emission plus §5 aggregation, in one pass
        over the same processor outputs — no second traversal, no second
        read of what a processor produced."""
        outputs = self.processor_telemetry.dispatch_and_emit(event)
        for out in outputs:
            self.aggregator.record(out)
        return outputs

    def observe(self, event: HextObject) -> None:
        """Feed an already-produced event (e.g. published by a caller
        outside this Telemetry Runtime's own dispatch loop, such as CTS-21's
        own pipeline wiring) into the Metric Aggregator, without
        re-dispatching it through any processor. Idempotent for
        non-`semantic.metric` types (a no-op, per `MetricAggregator.record`)."""
        self.aggregator.record(event)
