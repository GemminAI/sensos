from app.models.adapter_health import AdapterHealth, AdapterHealthStatus


class InMemoryAdapter:
    """The registry's fallback StorageAdapter for any unrecognized storage_class.

    Functional (dict-backed), unlike the other stub adapters -- proves the
    StorageAdapter interface end-to-end without a real physical store.
    """

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def connect(self) -> None:
        pass

    def write(self, key: str, payload: bytes) -> bool:
        self._store[key] = payload
        return True

    def read(self, key: str) -> bytes | None:
        return self._store.get(key)

    def health(self) -> AdapterHealth:
        return AdapterHealth(name="in_memory", status=AdapterHealthStatus.HEALTHY)
