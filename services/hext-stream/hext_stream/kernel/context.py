"""RFC-HEXT011 §6: Kernel Context — the single authoritative runtime state.

Every fact exposed here is delegated to whichever component already owns
it (the state machine, the Sequence Allocator, the Processor Registry, the
Stream Runtime) — this module stores nothing of its own. Per §6.1, that is
the point: a prior version of this kernel had ``RuntimeScheduler`` keep its
own "last admitted sequence per stream" record in parallel with the
Sequence Allocator's own counters, and the two could in principle drift.
``KernelContext`` exists so that never happens again, for this fact or any
other kernel-state fact future subsystems (Telemetry Runtime, Trajectory
Runtime, DevTools) need to read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hext_stream.kernel.state_machine import KernelState, KernelStateMachine
from hext_stream.processors.base import HEXTProcessor
from hext_stream.processors.registry import ProcessorRegistry
from hext_stream.runtime.stream_runtime import StreamRuntime
from hext_stream.streamrt.lifecycle import StreamLifecycleManager, StreamLifecycleState

if TYPE_CHECKING:
    # Avoids a circular import: hext_stream.trajectory.snapshot imports
    # KernelContext from this module, so this module cannot import
    # TrajectoryManager at runtime — only for type-checking.
    from hext_stream.trajectory.manager import TrajectoryManager
    from hext_stream.theory.manager import TheoryManager


class KernelContext:
    """RFC-HEXT011 §6: read-only facade over kernel state.

    Exposes no mutator (§6.3) — every state change happens through
    ``ExecutionKernel``'s own lifecycle methods, never through a
    ``KernelContext`` reference.
    """

    def __init__(
        self,
        *,
        state_machine: KernelStateMachine,
        runtime: StreamRuntime,
        processor_registry: ProcessorRegistry,
        lifecycle_manager: StreamLifecycleManager | None = None,
    ) -> None:
        self._state_machine = state_machine
        self._runtime = runtime
        self._processor_registry = processor_registry
        # RFC-HEXT012 §4.3: stream lifecycle is a Kernel Context fact like
        # any other — sourced from exactly one manager, never re-tracked.
        self._lifecycle_manager = lifecycle_manager or StreamLifecycleManager()
        # RFC-HEXT015 §5.2: a *reference*, not ownership — trajectory
        # state lives inside the TrajectoryManager, not here. Bound once,
        # after construction, by ExecutionKernel (see _bind_trajectory_manager),
        # since TrajectoryManager's own construction needs this KernelContext.
        self._trajectory_manager: "TrajectoryManager | None" = None
        # RFC-HEXT016 §5.2: identical reference relationship for theory
        # state — bound once, by ExecutionKernel, via _bind_theory_manager.
        self._theory_manager: "TheoryManager | None" = None

    @property
    def state(self) -> KernelState:
        """§6.2 Rule 1: current execution state."""
        return self._state_machine.state

    def last_sequence(self, stream: str) -> int | None:
        """§6.2 Rule 2: per-stream last-allocated sequence.

        Delegates to the Sequence Allocator ([RFC-HEXT013] §5.2) that
        ``StreamRuntime.publish`` already stamps every object with; this
        method does not maintain its own counter.
        """
        allocated = self._runtime.sequence_allocator.peek(stream)
        return allocated - 1 if allocated > 0 else None

    def processors(self) -> list[HEXTProcessor]:
        """§6.2 Rule 3: the registered Processor set."""
        return self._processor_registry.list()

    def health(self) -> dict[str, Any]:
        """§6.2 Rule 4: backend/runtime health."""
        return self._runtime.health()

    def metrics(self) -> dict[str, Any]:
        """§6.2 Rule 4: runtime metrics."""
        return self._runtime.metrics_dict()

    def queue_length(self, topic: str) -> int:
        """[RFC-HEXT012] §2 Rule 7 / [RFC-HEXT014] §6 Rule 3: the bound
        adapter's own queue depth for ``topic`` — read through the Stream
        Runtime, not tracked a second time here."""
        return self._runtime.backend.queue_depth(topic)

    def stream_lifecycle(self, topic: str) -> StreamLifecycleState | None:
        """[RFC-HEXT012] §4.3: current lifecycle state of a stream.

        Delegates to the one ``StreamLifecycleManager`` the Execution
        Kernel's Stream Runtime integration owns; returns ``None`` if the
        topic has never been created.
        """
        return self._lifecycle_manager.state(topic)

    def streams(self) -> list[str]:
        """[RFC-HEXT012] §4.3 / [RFC-HEXT014] §6 Rule 2: known stream names."""
        return self._lifecycle_manager.streams()

    @property
    def lifecycle_manager(self) -> StreamLifecycleManager:
        """The single ``StreamLifecycleManager`` instance — exposed so the
        Stream Runtime integration can drive transitions; read access
        elsewhere should prefer ``stream_lifecycle``/``streams`` above.
        """
        return self._lifecycle_manager

    @property
    def trajectory_manager(self) -> "TrajectoryManager":
        """[RFC-HEXT015] §5.2 Rule 1: a reference to the one Trajectory
        Manager instance. Trajectory state (snapshots, branches, replay
        positions) lives inside that object, not here — this Kernel
        Context does not own it (§5.2 Rule 2)."""
        if self._trajectory_manager is None:
            raise RuntimeError("TrajectoryManager has not been bound yet")
        return self._trajectory_manager

    def _bind_trajectory_manager(self, manager: "TrajectoryManager") -> None:
        """Internal, one-time wiring step used by ``ExecutionKernel``
        during its own construction — not a general-purpose mutator.
        [RFC-HEXT015] §5.2's reference relationship is established here,
        exactly once, since ``TrajectoryManager``'s own construction
        needs a ``KernelContext`` reference that must already exist."""
        if self._trajectory_manager is not None:
            raise RuntimeError("TrajectoryManager is already bound")
        self._trajectory_manager = manager

    @property
    def theory_manager(self) -> "TheoryManager":
        """[RFC-HEXT016] §5.2 Rule 1: a reference to the one Theory
        Manager instance. Theory-registration and current-selection state
        lives inside that object, not here (§5.2 Rule 2)."""
        if self._theory_manager is None:
            raise RuntimeError("TheoryManager has not been bound yet")
        return self._theory_manager

    def _bind_theory_manager(self, manager: "TheoryManager") -> None:
        """Internal, one-time wiring step — identical pattern to
        ``_bind_trajectory_manager`` above, per [RFC-HEXT011] §6.2's
        recognition that pattern (b) is now used identically by two RFCs."""
        if self._theory_manager is not None:
            raise RuntimeError("TheoryManager is already bound")
        self._theory_manager = manager
