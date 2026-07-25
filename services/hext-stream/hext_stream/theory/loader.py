"""RFC-HEXT016 §4: Theory Loader.

Ingests a raw `theory.config` payload and either registers a validated,
resolved `TheoryConfig` into the Theory Registry, or rejects it. Mirrors
the Registry/Loader division of labor RFC-HEXT006/RFC-HEXT009 already fix
for packages (§1.1): the Registry (§3) only ever stores an already-
resolved result, and this module is the one place that resolution happens.
"""

from __future__ import annotations

from hext_stream.observation.allocators import compute_payload_digest
from hext_stream.theory.config import RECOGNIZED_COEFFICIENTS, TheoryConfig
from hext_stream.theory.registry import TheoryRegistry


class TheoryLoaderError(Exception):
    """Base class for every `THEORY_ERR_*` rejection raised by the Loader."""

    code: str = "THEORY_ERR_UNKNOWN"

    def __init__(self, message: str) -> None:
        super().__init__(f"{self.code}: {message}")


class UnknownCoefficientError(TheoryLoaderError):
    """§4 Rule 1: unrecognized processor-name or coefficient-name key."""

    code = "THEORY_ERR_UNKNOWN_COEFFICIENT"


class InvalidCoefficientTypeError(TheoryLoaderError):
    """§4 Rule 2: a coefficient value that is not a number."""

    code = "THEORY_ERR_INVALID_COEFFICIENT_TYPE"


class UnknownParentError(TheoryLoaderError):
    """§4 Rule 5: `parent` does not name an already-registered `theory_id`."""

    code = "THEORY_ERR_UNKNOWN_PARENT"


class CircularParentError(TheoryLoaderError):
    """§4 Rule 6: the candidate's parent chain revisits its own `theory_id`."""

    code = "THEORY_ERR_CIRCULAR_PARENT"


class TheoryLoader:
    """RFC-HEXT016 §4."""

    def __init__(self, *, registry: TheoryRegistry) -> None:
        self.registry = registry

    def load(self, raw: dict) -> TheoryConfig:
        """Validate, resolve, hash, and register one `theory.config` payload.

        `raw` is the as-submitted shape (§2): `processor_overrides` is this
        theory's own (not yet parent-merged), `canonical_hash` absent. The
        registered, returned `TheoryConfig` is the *stored* shape: flat,
        parent-merged `processor_overrides` and a populated `canonical_hash`
        (§4 Rule 7).
        """
        raw_overrides = raw.get("processor_overrides") or {}
        # Validated against the raw dict, before Pydantic construction:
        # Pydantic's own float coercion would otherwise raise a generic
        # `ValidationError` for a bad type, or silently coerce a numeric
        # string, before this method's own `THEORY_ERR_*` checks ever run.
        self._validate_overrides(raw_overrides)

        candidate = TheoryConfig(
            theory_id=raw["theory_id"],
            version=raw["version"],
            parent=raw.get("parent"),
            processor_overrides=raw_overrides,
        )

        resolved_overrides = self._resolve_parent_chain(candidate)
        canonical_hash = compute_payload_digest(resolved_overrides)

        resolved = TheoryConfig(
            theory_id=candidate.theory_id,
            version=candidate.version,
            parent=candidate.parent,
            processor_overrides=resolved_overrides,
            canonical_hash=canonical_hash,
        )
        self.registry.register(resolved)
        return resolved

    def _validate_overrides(self, processor_overrides: dict[str, dict[str, float]]) -> None:
        """§4 Rules 1-2."""
        for processor, coefficients in processor_overrides.items():
            recognized = RECOGNIZED_COEFFICIENTS.get(processor)
            if recognized is None:
                raise UnknownCoefficientError(f"unrecognized processor {processor!r}")
            for name, value in coefficients.items():
                if name not in recognized:
                    raise UnknownCoefficientError(f"unrecognized coefficient {processor}.{name!r}")
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise InvalidCoefficientTypeError(f"{processor}.{name} must be a number, got {value!r}")

    def _resolve_parent_chain(self, candidate: TheoryConfig) -> dict[str, dict[str, float]]:
        """§2 Rule 5 / §4 Rules 5-7: walk `parent` back to its root, checking
        existence (Rule 5) and detecting a cycle back to `candidate.theory_id`
        (Rule 6), then merge child-overrides-win, transitively, into one flat
        map. `candidate` itself is not yet registered, so its own entry is
        never looked up in the Registry during this walk."""
        chain: list[TheoryConfig] = [candidate]
        visited: set[str] = {candidate.theory_id}

        parent_id = candidate.parent
        while parent_id is not None:
            if parent_id in visited:
                raise CircularParentError(
                    f"parent chain of {candidate.theory_id!r} revisits {parent_id!r}"
                )
            parent_config = self.registry.get(parent_id)
            if parent_config is None:
                raise UnknownParentError(f"parent {parent_id!r} is not registered")
            chain.append(parent_config)
            visited.add(parent_id)
            parent_id = parent_config.parent

        # Merge root-to-leaf so a child's own overrides win over its parent's.
        merged: dict[str, dict[str, float]] = {}
        for config in reversed(chain):
            for processor, coefficients in config.processor_overrides.items():
                merged.setdefault(processor, {}).update(coefficients)
        return merged
