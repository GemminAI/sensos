"""RFC-HEXT013 §7: Observation Grounding.

Scoping note (Phase 1 implementation): RFC-HEXT013 §7 Rule 2 (sort binding
against an active signature package) depends on the package loader of
RFC-HEXT006/RFC-HEXT009, which the runtime-alignment audit for this project
confirmed does not exist anywhere in the reference runtime yet. That check
is therefore not implemented here — it is a Specification Gap, recorded as
a TODO in the Phase 1 report, not silently skipped without record.

What this module does implement is §7 Rule 1's directional-constraint
check, narrowed to what is structurally verifiable without a package
loader: an object that declares a ``metadata.parent_id`` MUST name a
non-empty identifier, since an edge to nothing is exactly the "edge
referencing a node outside the object's own subgraph" failure mode RFC-
HEXT001 §6.3 already treats as a malformed frame.
"""

from __future__ import annotations

from typing import Any

from hext_stream.observation.errors import UngroundedError


def ground(*, metadata: dict[str, Any]) -> None:
    """RFC-HEXT013 §7 Rule 1: verify the Observation Directional Constraint.

    Raises ``UngroundedError`` (``OBS_ERR_UNGROUNDED``) on violation.
    Performs no mutation — grounding is verification-only, per §7 Rule 3.
    """
    if "parent_id" in metadata:
        parent_id = metadata["parent_id"]
        if parent_id is not None and (not isinstance(parent_id, str) or not parent_id.strip()):
            raise UngroundedError(
                f"metadata.parent_id must be a non-empty string or None, got {parent_id!r}"
            )
