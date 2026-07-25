"""Knowledge Runtime wiring: holds the active backend instances and hands
them to the API layer via dependency injection (see app/api/deps.py).

Future runtime responsibilities -- Knowledge Graph traversal, Vector
Search, Background Jobs, Authentication/Authorization -- are TODO and not
wired here yet.
"""

from app.storage.in_memory import InMemoryStorageBackend
from app.storage.protocol import StorageBackend


class Runtime:
    def __init__(self, storage: StorageBackend) -> None:
        self.storage = storage


_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = Runtime(storage=InMemoryStorageBackend())
    return _runtime
