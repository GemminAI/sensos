"""RFC-HEXT015 Trajectory Runtime."""

from __future__ import annotations

from hext_stream.trajectory.branch import (
    BranchAlreadyExistsError,
    BranchHandle,
    BranchManager,
    BranchViolationError,
)
from hext_stream.trajectory.diff import ControllerDelta, EventDelta, MetricDelta, Summary, TheoryDiff
from hext_stream.trajectory.manager import TrajectoryManager
from hext_stream.trajectory.replay import ReplayHandle, ReplayOrchestrator, ReplayResult
from hext_stream.trajectory.snapshot import SnapshotHandle, SnapshotManager
from hext_stream.theory.errors import TheorySwitchingNotImplementedError

__all__ = [
    "BranchAlreadyExistsError",
    "BranchHandle",
    "BranchManager",
    "BranchViolationError",
    "TrajectoryManager",
    "ReplayHandle",
    "ReplayOrchestrator",
    "ReplayResult",
    "TheoryDiff",
    "MetricDelta",
    "ControllerDelta",
    "EventDelta",
    "Summary",
    "TheorySwitchingNotImplementedError",
    "SnapshotHandle",
    "SnapshotManager",
]
