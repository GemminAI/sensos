from app.runtime.registry import get_runtime
from app.storage.protocol import StorageBackend


def get_storage_backend() -> StorageBackend:
    return get_runtime().storage
