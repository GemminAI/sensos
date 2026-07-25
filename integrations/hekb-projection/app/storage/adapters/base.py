from typing import Protocol, runtime_checkable

from app.models.adapter_health import AdapterHealth


@runtime_checkable
class StorageAdapter(Protocol):
    """The physical-storage interface every ProjectionBackend target sits behind.

    Concrete backends (PostgreSQL, ScyllaDB, MinIO, ...) are stubs in this
    phase -- connect()/write()/read() raise NotImplementedError. Only
    InMemoryAdapter (app/storage/adapters/in_memory.py) is functional.
    """

    def connect(self) -> None: ...

    def write(self, key: str, payload: bytes) -> bool: ...

    def read(self, key: str) -> bytes | None: ...

    def health(self) -> AdapterHealth: ...
