"""RFC-HEXT011: Runtime Execution Kernel.

Composes ``StreamRuntime`` (unchanged) with the state machine (§2),
Runtime Scheduler (§3), Processor Dispatcher (§4), Semantic Scheduler
(§5), and Kernel Context (§6) this RFC defines, per the target architecture:

    Observation Runtime -> Stream Runtime -> Execution Kernel (this module)
    -> Processor Pipeline -> Telemetry Runtime

Phase 1 scoping note: ``boot()`` performs only the BOOT -> LOAD -> READY
macro-state transitions RFC-HEXT011 §2.1 maps onto RFC-HEXT010 §3's ten
boot states. The granular RFC-HEXT010 stages themselves (Cryptographic
Verification, Dependency Resolution, Capability Matching, Orthogonal
Memory Allocation, Bridge Morphism Binding, Processor/Telemetry
Registration) are not implemented here, since they depend on the package
loader of RFC-HEXT006/RFC-HEXT009, which the runtime-alignment audit for
this project confirmed does not exist anywhere in the reference runtime.
This is recorded as a Specification Gap in the Phase 1 report, not silently
elided — ``boot()`` does not claim to perform those steps.
"""

from __future__ import annotations

import threading

from hext_stream.kernel.context import KernelContext
from hext_stream.kernel.dispatcher import ProcessorDispatcher
from hext_stream.kernel.scheduler import RuntimeScheduler
from hext_stream.kernel.semantic_scheduler import SemanticScheduler
from hext_stream.kernel.state_machine import KernelState, KernelStateMachine
from hext_stream.processors.registry import ProcessorRegistry
from hext_stream.runtime.stream_runtime import StreamRuntime
from hext_stream.schema.base import HextObject
from hext_stream.streamrt.lifecycle import StreamLifecycleManager, StreamLifecycleState
from hext_stream.streamrt.router import MessageRouter
from hext_stream.telemetry.api import TelemetryAPI
from hext_stream.telemetry.runtime import TelemetryRuntime
from hext_stream.devtools.inspector import HEXTInspector
from hext_stream.trajectory.branch import BranchManager
from hext_stream.trajectory.manager import TrajectoryManager
from hext_stream.trajectory.replay import ReplayOrchestrator
from hext_stream.trajectory.snapshot import SnapshotManager
from hext_stream.theory.manager import TheoryManager


class KernelNotRunningError(Exception):
    """Raised when publish is attempted outside the RUNNING state."""


class ExecutionKernel:
    """RFC-HEXT011: the runtime's steady-state execution lifecycle.

    Owns exactly one ``KernelContext`` (§6.4) and shares that same
    instance with every internal component that needs to read kernel
    state (``RuntimeScheduler``, today) — and, in later phases, with
    Telemetry Runtime, Trajectory Runtime, and DevTools. No component
    holds its own copy of a fact the Kernel Context already exposes
    (§6.1/§9 Rule 4).
    """

    def __init__(
        self,
        runtime: StreamRuntime,
        *,
        processor_registry: ProcessorRegistry | None = None,
    ) -> None:
        self.runtime = runtime
        self.state_machine = KernelStateMachine()
        self._processor_registry = processor_registry or ProcessorRegistry()
        self.dispatcher = ProcessorDispatcher(self._processor_registry)
        # RFC-HEXT012 §4: one lifecycle manager, shared via the Kernel
        # Context (§4.3) — not tracked a second time by this class.
        self._lifecycle_manager = StreamLifecycleManager()
        self.router = MessageRouter(self.runtime.router)
        # RFC-HEXT011 §6.4: exactly one Kernel Context per Execution
        # Kernel, shared by reference — never copied — with every
        # consumer that needs kernel state.
        self.context = KernelContext(
            state_machine=self.state_machine,
            runtime=self.runtime,
            processor_registry=self._processor_registry,
            lifecycle_manager=self._lifecycle_manager,
        )
        self.scheduler = RuntimeScheduler(self.context)
        # RFC-HEXT015 §5.2: TrajectoryManager is constructed with a
        # reference to this same KernelContext (for SnapshotManager's
        # current_sequence_bound), then bound onto the context itself —
        # a reference, never ownership; trajectory state lives in these
        # three managers, not inside KernelContext.
        self._trajectory_manager = TrajectoryManager(
            snapshot_manager=SnapshotManager(history_fn=self.runtime.history, context=self.context),
            replay_orchestrator=ReplayOrchestrator(
                history_fn=self.runtime.history,
                replay_from_timestamp_fn=self.runtime.replay_engine.replay_from_timestamp,
                replay_last_n_fn=self.runtime.replay_engine.replay_last_n,
            ),
            branch_manager=BranchManager(),
        )
        self.context._bind_trajectory_manager(self._trajectory_manager)
        # RFC-HEXT016 §5.2: identical reference relationship for theory
        # state. TheoryManager needs no KernelContext reference of its own
        # (it has no fact to read through one, unlike SnapshotManager).
        self._theory_manager = TheoryManager()
        self.context._bind_theory_manager(self._theory_manager)
        # RFC-HEXT014: Telemetry Runtime publishes via StreamRuntime.publish
        # directly (not self.publish below), since it must be able to
        # report BOOT/LOAD state before the kernel ever reaches RUNNING.
        self.runtime.router.register("Telemetry")
        self._telemetry = TelemetryRuntime(
            registry=self._processor_registry,
            state_machine=self.state_machine,
            context=self.context,
            publish_fn=self.runtime.publish,
            history_fn=self.runtime.history,
        )
        self.telemetry = TelemetryAPI(self._telemetry)
        # RFC-HEXT008: HEXT Inspector is constructed with the Telemetry
        # API and Kernel Context only — never a Runtime/ExecutionKernel
        # reference — per this phase's "no direct Runtime access" rule.
        # Task 10: trajectory display reads context.trajectory_manager,
        # which HEXTInspector reaches through the same context reference.
        self.devtools = HEXTInspector(telemetry=self.telemetry, context=self.context)
        self.semantic_scheduler = SemanticScheduler()
        # Serializes kernel-mediated publish() calls so that recovering the
        # sequence StreamRuntime.publish() just assigned (via the Kernel
        # Context) cannot race against another kernel-mediated publish to
        # the same topic. This does not — and cannot — order publishes
        # that bypass the kernel and call StreamRuntime.publish() directly
        # (e.g. CTS fixtures, Processor Pipeline output);
        # RuntimeScheduler.admit() only guarantees ordering among
        # admissions that pass through it.
        self._publish_lock = threading.Lock()

    @property
    def state(self) -> KernelState:
        return self.context.state

    def boot(self) -> KernelState:
        """RFC-HEXT011 §2: BOOT -> LOAD -> READY. See module docstring for
        Phase 1 scoping — this performs the macro-state transitions only."""
        self.state_machine.transition(KernelState.LOAD)
        return self.state_machine.transition(KernelState.READY)

    def start(self) -> KernelState:
        """RFC-HEXT011 §2.2 Rule 1: READY -> RUNNING."""
        return self.state_machine.transition(KernelState.RUNNING)

    def pause(self) -> KernelState:
        """RFC-HEXT011 §2.2 Rule 2: RUNNING -> PAUSED."""
        return self.state_machine.transition(KernelState.PAUSED)

    def resume(self) -> KernelState:
        """RFC-HEXT011 §2.2 Rule 2: PAUSED -> RUNNING."""
        return self.state_machine.transition(KernelState.RUNNING)

    def shutdown(self) -> KernelState:
        """RFC-HEXT011 §2.2 Rule 3: RUNNING or PAUSED -> SHUTDOWN."""
        return self.state_machine.transition(KernelState.SHUTDOWN)

    def dispatch_with_telemetry(self, event: HextObject) -> list[HextObject]:
        """Dispatch ``event`` to every registered Processor that consumes
        its type, emitting RFC-HEXT014 §3.1-3.3 telemetry and feeding the
        Metric Aggregator (§5), in one pass. Distinct from
        ``self.dispatcher.dispatch_strict`` (RFC-HEXT011 §4's narrower,
        six-entry-point-only dispatcher, unchanged from Phase 1): this
        method dispatches any registered processor, matching what the
        EXP-4010 semantic chain and the Telemetry Runtime both need."""
        return self._telemetry.dispatch_and_emit(event)

    def _ensure_active(self, topic: str) -> None:
        """RFC-HEXT012 §4.1: drive Created -> Connected -> Active on a
        stream's first touch. A stream already Active or Paused is left
        alone; a Closed stream is not reopened (the caller's publish will
        still be attempted, and fail at the adapter/router level, which is
        the correct place for that error to surface)."""
        state = self._lifecycle_manager.create(topic)
        if state == StreamLifecycleState.CREATED:
            self._lifecycle_manager.transition(topic, StreamLifecycleState.CONNECTED)
            state = StreamLifecycleState.CONNECTED
        if state == StreamLifecycleState.CONNECTED:
            self._lifecycle_manager.transition(topic, StreamLifecycleState.ACTIVE)

    def publish(self, topic: str, obj: HextObject) -> str:
        """RFC-HEXT011 §3: admit and publish, enforced only while RUNNING
        (§2.2 Rule 2's "no admission while PAUSED", generalized to every
        non-RUNNING state)."""
        if self.context.state != KernelState.RUNNING:
            raise KernelNotRunningError(
                f"cannot publish while kernel state is {self.context.state.value}"
            )
        with self._publish_lock:
            # Validate before touching lifecycle state, so an unregistered
            # topic (rejected by the same TopicRouter StreamRuntime.publish
            # itself uses) never leaves a stray Active lifecycle entry
            # behind for a topic that was never actually bound.
            self.router.resolve_topic(topic=topic)
            self._ensure_active(topic)
            event_id = self.runtime.publish(topic, obj)
            sequence = self.context.last_sequence(topic)
            self.scheduler.admit(topic, sequence)
        return event_id
