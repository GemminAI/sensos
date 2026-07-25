from typing import Protocol, runtime_checkable

from app.models.storage_profile import StorageProfile


@runtime_checkable
class StorageBackend(Protocol):
    """The storage abstraction every HEKB Runtime module depends on.

    Concrete backends (LMDB, ScyllaDB, PostgreSQL, Redis, ...) are not
    implemented in this phase -- only InMemoryStorageBackend exists today.
    """

    def profile(self) -> StorageProfile:
        """Return this backend's declarative StorageProfile."""
        ...
