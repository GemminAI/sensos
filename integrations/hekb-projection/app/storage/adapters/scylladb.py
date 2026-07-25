from app.models.adapter_health import AdapterHealth, AdapterHealthStatus


class ScyllaDBAdapter:
    """Stub StorageAdapter for the append_only storage_class.

    TODO (next phase): real ScyllaDB connection, write, and read.
    """

    def connect(self) -> None:
        raise NotImplementedError

    def write(self, key: str, payload: bytes) -> bool:
        raise NotImplementedError

    def read(self, key: str) -> bytes | None:
        raise NotImplementedError

    def health(self) -> AdapterHealth:
        return AdapterHealth(
            name="scylladb",
            status=AdapterHealthStatus.NOT_IMPLEMENTED,
            detail="ScyllaDB adapter is a stub; not implemented yet.",
        )
