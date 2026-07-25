"""RFC-HEXT011 Runtime Execution Kernel."""

from __future__ import annotations

from hext_stream.kernel.context import KernelContext
from hext_stream.kernel.dispatcher import KernelUnroutableTypeError, ProcessorDispatcher
from hext_stream.kernel.execution_kernel import ExecutionKernel, KernelNotRunningError
from hext_stream.kernel.scheduler import RuntimeScheduler, SchedulerOrderViolation
from hext_stream.kernel.semantic_scheduler import GateDecision, SemanticScheduler
from hext_stream.kernel.state_machine import KernelState, KernelStateMachine, KernelTransitionError

__all__ = [
    "ExecutionKernel",
    "KernelContext",
    "KernelNotRunningError",
    "KernelState",
    "KernelStateMachine",
    "KernelTransitionError",
    "KernelUnroutableTypeError",
    "ProcessorDispatcher",
    "RuntimeScheduler",
    "SchedulerOrderViolation",
    "SemanticScheduler",
    "GateDecision",
]
