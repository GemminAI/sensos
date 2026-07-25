"""RFC-HEXT016 §2: the `theory.config` wire schema.

Recognized processor/coefficient names, per §2 Rule 3's baseline values —
these are the only keys the Theory Loader (§4) will accept; listed here so
`TheoryConfig` construction and the Registry can already validate against
them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# RFC-HEXT016 §2 Rule 3 — processor name -> {coefficient name: baseline value}.
# The baseline values live in each processor's own module (e.g.
# gain_scheduler.py's ALPHA); this dict exists only to name which keys are
# recognized, not to duplicate the source of truth for their values.
RECOGNIZED_COEFFICIENTS: dict[str, frozenset[str]] = {
    "gain": frozenset({"alpha"}),
    "controller": frozenset({"allow_threshold", "warn_threshold"}),
    "lcf": frozenset({"empty_constraints_default"}),
    "if": frozenset({"empty_required_default"}),
    "oi": frozenset({"zero_denominator_default"}),
}


class TheoryConfig(BaseModel):
    """RFC-HEXT016 §2. Two shapes coexist under this one class:

    - As *submitted* (raw `theory.config` HextObject payload): `parent` may
      reference an unresolved parent, `processor_overrides` is this
      theory's own, and `canonical_hash` is absent/None.
    - As *stored* in the Theory Registry (post-Loader, RFC-HEXT016 §4
      Rule 7): `processor_overrides` is the flat, parent-merged result,
      and `canonical_hash` is populated. The Registry only ever holds the
      stored shape — see `TheoryLoader` for the transformation between them.
    """

    theory_id: str
    version: str
    parent: str | None = None
    processor_overrides: dict[str, dict[str, float]] = Field(default_factory=dict)
    # RFC-HEXT016 §2 Rule 6: Loader-computed, never submitter-supplied in
    # practice — present here so the *stored* shape can carry it.
    canonical_hash: str | None = None
