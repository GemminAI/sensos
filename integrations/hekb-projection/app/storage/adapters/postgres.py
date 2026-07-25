from app.models.adapter_health import AdapterHealth, AdapterHealthStatus


class PostgresAdapter:
    """Stub StorageAdapter for the relational storage_class.

    TODO (next phase): real PostgreSQL connection, write, and read.
    """

    def connect(self) -> None:
        raise NotImplementedError

    def write(self, key: str, payload: bytes) -> bool:
        raise NotImplementedError

    def read(self, key: str) -> bytes | None:
        raise NotImplementedError

    def health(self) -> AdapterHealth:
        return AdapterHealth(
            name="postgres",
            status=AdapterHealthStatus.NOT_IMPLEMENTED,
            detail="PostgreSQL adapter is a stub; not implemented yet.",
        )
