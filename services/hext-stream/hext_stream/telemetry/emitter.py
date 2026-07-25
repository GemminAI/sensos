"""RFC-HEXT014 §3.1-3.3, §3.6: emission of processor lifecycle and kernel
state telemetry.

Composes over the existing ``ProcessorRegistry`` and ``KernelStateMachine``
(both untouched, except for ``KernelStateMachine``'s additive listener hook
added alongside this module) rather than modifying ``Pipeline.execute()``
or ``ProcessorRegistry.dispatch()`` — the same wrap-don't-rewrite pattern
Phase 1's ``ProcessorDispatcher`` already established.
"""

from __future__ import annotations

from typing import Callable

from hext_stream.kernel.state_machine import KernelState, KernelStateMachine
from hext_stream.processors.registry import ProcessorRegistry
from hext_stream.schema.base import HextObject
from hext_stream.telemetry import events

PublishFn = Callable[[str, HextObject], str]


class ProcessorTelemetry:
    """RFC-HEXT014 §3.1-3.3: processor.started/completed/failed emission.

    ``dispatch_and_emit`` mirrors ``ProcessorRegistry.dispatch``'s own
    iterate-processors-that-consume-this-type loop (reading only the
    public ``processor.consumes`` attribute and the public
    ``ProcessorRegistry.list()`` — no private state touched), adding the
    telemetry emission §4 requires around each processor invocation.
    """

    def __init__(
        self,
        registry: ProcessorRegistry,
        publish_fn: PublishFn,
        *,
        telemetry_topic: str = "Telemetry",
        source: str = "telemetry-runtime",
    ) -> None:
        self._registry = registry
        self._publish = publish_fn
        self._topic = telemetry_topic
        self._source = source

    def dispatch_and_emit(self, event: HextObject) -> list[HextObject]:
        outputs: list[HextObject] = []
        for processor in self._registry.list():
            if event.type not in processor.consumes:
                continue
            self._publish(
                self._topic,
                events.processor_started(
                    source=self._source,
                    processor_id=processor.processor_id,
                    processor_type=processor.processor_type,
                    input_object_id=event.id,
                    parent_id=event.metadata.get("parent_id"),
                ),
            )
            try:
                proc_outputs, elapsed_ms = processor.process_timed(event)
            except Exception as exc:  # RFC-HEXT014 §4 Rule 2: never propagate uncaught.
                self._publish(
                    self._topic,
                    events.processor_failed(
                        source=self._source,
                        processor_id=processor.processor_id,
                        processor_type=processor.processor_type,
                        input_object_id=event.id,
                        error_code=type(exc).__name__,
                        error_message=str(exc),
                    ),
                )
                continue
            for out in proc_outputs:
                self._publish(
                    self._topic,
                    events.processor_completed(
                        source=self._source,
                        processor_id=processor.processor_id,
                        processor_type=processor.processor_type,
                        input_object_id=event.id,
                        output_object_id=out.id,
                        execution_time_ms=elapsed_ms,
                    ),
                )
                outputs.append(out)
        return outputs


class KernelStateTelemetry:
    """RFC-HEXT014 §3.6: emits `runtime.state` on every kernel transition.

    Registers as a listener on the existing ``KernelStateMachine``
    (Phase 1, untouched except for the additive ``add_listener`` hook) —
    publishes via the raw ``publish_fn`` (expected to be
    ``StreamRuntime.publish``, not ``ExecutionKernel.publish``) since state
    transitions occur before the kernel reaches RUNNING, and
    ``ExecutionKernel.publish`` is gated on RUNNING ([RFC-HEXT011] §3
    Rule 3) — telemetry must be able to report BOOT/LOAD states too.
    """

    def __init__(
        self,
        state_machine: KernelStateMachine,
        publish_fn: PublishFn,
        *,
        telemetry_topic: str = "Telemetry",
        source: str = "telemetry-runtime",
    ) -> None:
        self._publish = publish_fn
        self._topic = telemetry_topic
        self._source = source
        state_machine.add_listener(self._on_transition)

    def _on_transition(self, previous: KernelState, new: KernelState) -> None:
        self._publish(
            self._topic,
            events.runtime_state(source=self._source, state=new.value, previous_state=previous.value),
        )
