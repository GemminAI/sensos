"""RFC-HEXT016 §5.4: Theory Context.

The one object a processor receives to look up its own coefficient
overrides — never a raw `TheoryConfig`, never an individual coefficient
value passed positionally. Produced exclusively by `TheoryManager.context_for`
(§5.2/§9 Rule 3's "one resolution point").
"""

from __future__ import annotations


class TheoryContext:
    """RFC-HEXT016 §5.4. Immutable, resolved coefficient view.

    `TheoryContext.default()` carries no overrides — every `coefficient()`
    call on it returns the caller-supplied default, i.e. today's hardcoded
    literal. A processor given `theory_context=None` MUST behave exactly as
    if given `TheoryContext.default()` (§5.4 Rule 1); the processor-side
    code enforces this by resolving `None` to `TheoryContext.default()`
    once, at construction, so there is only ever one code path afterward.
    """

    def __init__(
        self,
        *,
        theory_id: str | None = None,
        processor_overrides: dict[str, dict[str, float]] | None = None,
        canonical_hash: str | None = None,
    ) -> None:
        self._theory_id = theory_id
        # RFC-HEXT016 §2 Rule 5: always the already-flat, parent-merged
        # map — this class never itself walks a parent chain (§9 Rule 8).
        self._processor_overrides: dict[str, dict[str, float]] = processor_overrides or {}
        # RFC-HEXT016 §5.4 Rule 4: carried straight through from the
        # Registry's stored TheoryConfig, never computed here.
        self._canonical_hash = canonical_hash

    @classmethod
    def default(cls) -> "TheoryContext":
        """RFC-HEXT016 §5.4 Rule 1: the baseline — no overrides, no hash."""
        return cls(theory_id=None, processor_overrides={}, canonical_hash=None)

    @property
    def theory_id(self) -> str | None:
        return self._theory_id

    @property
    def canonical_hash(self) -> str | None:
        return self._canonical_hash

    @property
    def is_default(self) -> bool:
        """True for both `TheoryContext.default()` and any context that
        happens to carry zero coefficient overrides — RFC-HEXT016 §5.4
        Rule 1 requires these be indistinguishable in *output*, not
        necessarily in this convenience flag, but a context with no
        overrides at all is always numerically the baseline regardless of
        its `theory_id` label."""
        return not self._processor_overrides

    def coefficient(self, processor: str, name: str, default: float) -> float:
        """RFC-HEXT016 §5.4 Rule 2: the only way a processor reads a
        coefficient. `default` is the processor's own existing hardcoded
        literal — never removed from the processor's source, always the
        fallback when this context has no override for
        `(processor, name)`."""
        return self._processor_overrides.get(processor, {}).get(name, default)
