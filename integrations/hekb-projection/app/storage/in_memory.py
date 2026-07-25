from app.models.storage_profile import StorageCapabilities, StorageProfile


class InMemoryStorageBackend:
    """A process-local, non-persistent StorageBackend implementation.

    Exists to prove StorageBackend is a genuinely swappable Protocol; holds
    no data of its own beyond what this phase requires (profile reporting).
    """

    def profile(self) -> StorageProfile:
        return StorageProfile(
            storage_class="in_memory",
            retention="none",
            capabilities=StorageCapabilities(
                transactions=False,
                ordered_write=False,
                sequential_scan=True,
                random_update=True,
            ),
            metadata={"backend": "python-dict", "persistent": False},
        )
