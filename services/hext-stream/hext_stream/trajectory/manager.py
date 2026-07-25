"""RFC-HEXT015 §5 (Task 9): Trajectory Manager — the Single Source of
Truth for trajectory state, composing Snapshot (§2/Task 6), Replay
(§3/Task 7), and Branch (§4/Task 8).

Per §5.2, the Kernel Context holds a *reference* to one instance of this
class; this class is where snapshot/branch/replay state actually lives,
not the Kernel Context.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from hext_stream.trajectory.branch import BranchHandle, BranchManager
from hext_stream.trajectory.replay import ReplayHandle, ReplayOrchestrator
from hext_stream.trajectory.snapshot import SnapshotHandle, SnapshotManager


@dataclass
class _CurrentSession:
    """RFC-HEXT008 §3.1/Task 10: the one place "what is the Inspector
    currently looking at" lives — inside the Trajectory Manager, per
    [RFC-HEXT015] §5.1, not duplicated into DevTools."""

    stream: str | None = None
    snapshot: SnapshotHandle | None = None
    branch_id: str | None = None
    replay_position: int | None = None


class TrajectoryManager:
    """RFC-HEXT015 §5: composition only — see §5.1. Owns no state beyond
    what `SnapshotManager`/`ReplayOrchestrator`/`BranchManager` already
    track; reads Kernel Context facts (e.g. current sequence bound)
    through the same reference those managers were given, per §5.3."""

    def __init__(
        self,
        *,
        snapshot_manager: SnapshotManager,
        replay_orchestrator: ReplayOrchestrator,
        branch_manager: BranchManager,
    ) -> None:
        self.snapshots = snapshot_manager
        self.replay = replay_orchestrator
        self.branches = branch_manager
        self._session = _CurrentSession()

    def snapshot_at_sequence(self, stream: str, sequence: int) -> SnapshotHandle:
        handle = self.snapshots.at_sequence(stream, sequence)
        self._session.stream = stream
        self._session.snapshot = handle
        return handle

    def snapshot_at_timestamp(self, stream: str, timestamp: datetime) -> SnapshotHandle:
        handle = self.snapshots.at_timestamp(stream, timestamp)
        self._session.stream = stream
        self._session.snapshot = handle
        return handle

    def replay_from_sequence(self, stream: str, sequence: int) -> ReplayHandle:
        self._session.stream = stream
        self._session.replay_position = sequence
        return self.replay.from_sequence(stream, sequence)

    def replay_from_timestamp(self, stream: str, timestamp: datetime) -> ReplayHandle:
        self._session.stream = stream
        return self.replay.from_timestamp(stream, timestamp)

    def replay_last_n(self, stream: str, n: int) -> ReplayHandle:
        self._session.stream = stream
        return self.replay.last_n(stream, n)

    def branch_from_snapshot(self, snapshot: SnapshotHandle, branch_id: str) -> BranchHandle:
        handle = self.branches.create(snapshot, branch_id)
        self._session.branch_id = branch_id
        return handle

    def branch(self, branch_id: str) -> BranchHandle | None:
        return self.branches.get(branch_id)

    def active_branches(self) -> list[str]:
        return self.branches.branches()

    def select_branch(self, branch_id: str | None) -> None:
        """RFC-HEXT008 Task 10: explicit selection, for an operator
        switching which branch the Inspector is currently viewing without
        creating a new one."""
        self._session.branch_id = branch_id

    def seek_replay(self, sequence: int) -> None:
        self._session.replay_position = sequence

    def session_view(self) -> dict[str, Any]:
        """RFC-HEXT008 Task 10: current trajectory, replay position,
        branch id, and snapshot id — all read from this one place."""
        snapshot = self._session.snapshot
        return {
            "current_trajectory": self._session.stream,
            "replay_position": self._session.replay_position,
            "branch_id": self._session.branch_id,
            "snapshot_id": snapshot.sequence_bound() if snapshot is not None else None,
        }
