"""RFC-HEXT016 §3: Theory Registry.

In-memory `theory_id -> TheoryConfig` lookup — no new persistent storage,
no new transport. Populated exclusively by the Theory Loader (§4). Per §3's
own text, every stored `TheoryConfig` is already parent-resolved and
hash-computed by the time `register()` is called — this class never
performs that resolution itself.
"""

from __future__ import annotations

import threading

from hext_stream.theory.config import TheoryConfig


class TheoryRegistry:
    """RFC-HEXT016 §3."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._configs: dict[str, TheoryConfig] = {}

    def register(self, config: TheoryConfig) -> None:
        """RFC-HEXT016 §4 Rule 4: idempotent for an identical
        (theory_id, version) pair; overwrites only on a version change."""
        with self._lock:
            existing = self._configs.get(config.theory_id)
            if existing is not None and existing.version == config.version:
                return
            self._configs[config.theory_id] = config

    def get(self, theory_id: str) -> TheoryConfig | None:
        with self._lock:
            return self._configs.get(theory_id)

    def theories(self) -> list[str]:
        with self._lock:
            return list(self._configs.keys())
