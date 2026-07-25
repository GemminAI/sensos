"""RFC-HEXT016 §5: Theory Manager — Single Source of Truth for
theory-related runtime state.
"""

from __future__ import annotations

from typing import Any

from hext_stream.schema.base import HextObject
from hext_stream.theory.context import TheoryContext
from hext_stream.theory.executor import TheoryExecutor, TheoryResult
from hext_stream.theory.loader import TheoryLoader
from hext_stream.theory.registry import TheoryRegistry


class TheoryNotRegisteredError(Exception):
    """Raised by `context_for` for an unrecognized `theory_id`.

    Deliberately not a silent fallback to the baseline: per the same
    observability discipline RFC-HEXT016 §4 Rule 1 already applies to the
    Theory Loader's coefficient validation, resolving an unknown
    `theory_id` to the default context would let an operator believe a
    theory is active when it silently is not.
    """


class TheoryManager:
    """RFC-HEXT016 §5: composes the Theory Registry (§3), the Theory Loader
    (§4), and the Theory Executor (§6). Owns the current-session
    `theory_id` selection (§5.3). Referenced, not owned, by `KernelContext`
    (§5.2)."""

    def __init__(self, *, registry: TheoryRegistry | None = None) -> None:
        self.registry = registry or TheoryRegistry()
        self.loader = TheoryLoader(registry=self.registry)
        self.executor = TheoryExecutor()
        self._session_theory_id: str | None = None

    def context_for(self, theory_id: str | None = None) -> TheoryContext:
        """RFC-HEXT016 §5.4 / §9 Rule 3: the one resolution point from
        `theory_id` to `TheoryContext`. `theory_id=None` always returns
        `TheoryContext.default()` — no registry lookup performed, since
        `None` unambiguously means "no theory"."""
        if theory_id is None:
            return TheoryContext.default()
        config = self.registry.get(theory_id)
        if config is None:
            raise TheoryNotRegisteredError(f"theory_id {theory_id!r} is not registered")
        return TheoryContext(
            theory_id=config.theory_id,
            processor_overrides=config.processor_overrides,
            canonical_hash=config.canonical_hash,
        )

    def execute_theory(self, theory_id: str | None, objects: list[HextObject]) -> TheoryResult:
        """RFC-HEXT016 §6.2 Rule 4: resolves `theory_id` via `context_for`
        (§9 Rule 3's one resolution point) and delegates to `self.executor`
        — no caller constructs a `TheoryExecutor` directly or holds its own
        `theory_id` -> `TheoryContext` mapping."""
        context = self.context_for(theory_id)
        return self.executor.execute(context, objects)

    def select_theory(self, theory_id: str | None) -> None:
        """RFC-HEXT008 Task 10-style session selection, mirroring
        `TrajectoryManager.select_branch`."""
        self._session_theory_id = theory_id

    def session_view(self) -> dict[str, Any]:
        return {"current_theory_id": self._session_theory_id}
