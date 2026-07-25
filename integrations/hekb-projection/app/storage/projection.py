from typing import Protocol, runtime_checkable

from app.models.storage_profile import StorageProfile


@runtime_checkable
class ProjectionBackend(Protocol):
    """Physical projection interface (design input: RFC-HEKB08 draft).

    Routes a StorageProfile-described payload to a concrete physical store.
    No implementation exists yet -- TODO: LMDB, ScyllaDB, PostgreSQL, Redis.
    """

    def write(self, profile: StorageProfile, payload: bytes) -> bool:
        """Persist payload according to profile's declared capabilities."""
        ...
