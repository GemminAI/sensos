from app.models.adapter_health import AdapterHealth, AdapterHealthStatus


class MinIOAdapter:
    """Stub StorageAdapter for the blob storage_class.

    TODO (next phase): real MinIO connection, write, and read.
    """

    def connect(self) -> None:
        raise NotImplementedError

    def write(self, key: str, payload: bytes) -> bool:
        raise NotImplementedError

    def read(self, key: str) -> bytes | None:
        raise NotImplementedError

    def health(self) -> AdapterHealth:
        return AdapterHealth(
            name="minio",
            status=AdapterHealthStatus.NOT_IMPLEMENTED,
            detail="MinIO adapter is a stub; not implemented yet.",
        )
