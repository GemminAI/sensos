from app.storage.adapters.base import StorageAdapter
from app.storage.adapters.in_memory import InMemoryAdapter
from app.storage.adapters.minio import MinIOAdapter
from app.storage.adapters.postgres import PostgresAdapter
from app.storage.adapters.scylladb import ScyllaDBAdapter


class AdapterRegistry:
    """Resolves a StorageProfile.storage_class to its StorageAdapter.

    Any storage_class not explicitly mapped (including the literal
    "unknown") falls back to InMemoryAdapter.
    """

    def __init__(self) -> None:
        self._default: StorageAdapter = InMemoryAdapter()
        self._by_storage_class: dict[str, StorageAdapter] = {
            "relational": PostgresAdapter(),
            "append_only": ScyllaDBAdapter(),
            "blob": MinIOAdapter(),
        }

    def resolve(self, storage_class: str) -> StorageAdapter:
        return self._by_storage_class.get(storage_class, self._default)

    def all(self) -> dict[str, StorageAdapter]:
        return {**self._by_storage_class, "unknown": self._default}


_registry: AdapterRegistry | None = None


def get_adapter_registry() -> AdapterRegistry:
    global _registry
    if _registry is None:
        _registry = AdapterRegistry()
    return _registry
