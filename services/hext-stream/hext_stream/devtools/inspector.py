"""RFC-HEXT008: HEXT Inspector — composes Tasks 1-5.

Constructed with a `TelemetryAPI` and a `KernelContext` only — never a
`StreamRuntime` or `ExecutionKernel` reference — enforcing this phase's
architectural rule at the type level: DevTools cannot reach Runtime
internals through this class because it is never given them.
"""

from __future__ import annotations

from hext_stream.devtools.event_log import EventLog
from hext_stream.devtools.oscilloscope import Oscilloscope
from hext_stream.devtools.processor_trace import ProcessorTrace
from hext_stream.devtools.replay_controller import ReplayController
from hext_stream.devtools.runtime_state_viewer import RuntimeStateViewer
from hext_stream.devtools.trajectory_view import TrajectoryView
from hext_stream.kernel.context import KernelContext
from hext_stream.telemetry.api import TelemetryAPI


class HEXTInspector:
    """RFC-HEXT008: the first working HEXT Inspector (Phase 3 scope —
    see the document's Phase 3 amendment note for what is and is not
    included)."""

    def __init__(self, *, telemetry: TelemetryAPI, context: KernelContext) -> None:
        self.processor_trace = ProcessorTrace(telemetry)
        self.event_log = EventLog(telemetry)
        self.oscilloscope = Oscilloscope(telemetry)
        self.runtime_state_viewer = RuntimeStateViewer(context)
        self.replay_controller = ReplayController(lambda: telemetry.event_log(limit=1000))
        # Task 10: current trajectory / replay position / branch id /
        # snapshot id, sourced exclusively from TrajectoryManager via the
        # Kernel Context reference (RFC-HEXT015 §5.2).
        self.trajectory_view = TrajectoryView(context)
