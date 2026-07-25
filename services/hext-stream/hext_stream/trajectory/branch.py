"""RFC-HEXT015 §4 (Task 8): Branch Manager.

Every branch shares its originating Snapshot's Observation history by
reference; a branch may diverge only in theory, local Execution Kernel
replay state, or derived semantic objects (§4 Rule 5) — never in
Observation. `append` enforces this at the type level: appending a
`type == "observation"` object is rejected.
"""

from __future__ import annotations

from hext_stream.schema.base import HextObject
from hext_stream.trajectory.snapshot import SnapshotHandle


class BranchViolationError(Exception):
    """RFC-HEXT015 §4 Rule 5: attempted to diverge Observation history."""


class BranchAlreadyExistsError(Exception):
    """RFC-HEXT015 §4 Rule 2: `branch_id` must be unique."""


class BranchHandle:
    """RFC-HEXT015 §4."""

    def __init__(self, *, branch_id: str, snapshot: SnapshotHandle) -> None:
        self._branch_id = branch_id
        self._snapshot = snapshot
        self._local_objects: list[HextObject] = []

    @property
    def branch_id(self) -> str:
        return self._branch_id

    def append(self, obj: HextObject) -> None:
        """§4 Rule 5: rejects Observation objects — a branch may only
        accumulate derived semantic objects. §4 Rule 2: stamps `branch_id`
        into `metadata` (via `model_copy`, not a mutation of `obj`)."""
        if obj.type == "observation":
            raise BranchViolationError(
                f"branch {self._branch_id!r}: cannot append an Observation "
                f"(RFC-HEXT015 §4 Rule 5 — Observation is never among a branch's permitted divergences)"
            )
        stamped = obj.model_copy(update={"metadata": {**obj.metadata, "branch_id": self._branch_id}})
        self._local_objects.append(stamped)

    def objects(self) -> list[HextObject]:
        """§4: "snapshot prefix + branch-local objects" — the shared
        Observation history (by reference, per [RFC-HEXT015] §2 Rule 2)
        followed by this branch's own derived objects."""
        return self._snapshot.objects() + list(self._local_objects)


class BranchManager:
    """RFC-HEXT015 §4 / Task 8."""

    def __init__(self) -> None:
        self._branches: dict[str, BranchHandle] = {}

    def create(self, snapshot: SnapshotHandle, branch_id: str) -> BranchHandle:
        if branch_id in self._branches:
            raise BranchAlreadyExistsError(f"branch_id {branch_id!r} already exists")
        handle = BranchHandle(branch_id=branch_id, snapshot=snapshot)
        self._branches[branch_id] = handle
        return handle

    def get(self, branch_id: str) -> BranchHandle | None:
        return self._branches.get(branch_id)

    def discard(self, branch_id: str) -> None:
        """§4 Rule 4: discarding a branch has no effect on the trunk
        stream or any other branch — it is simply removed from this
        manager's own tracking."""
        self._branches.pop(branch_id, None)

    def branches(self) -> list[str]:
        return list(self._branches.keys())
