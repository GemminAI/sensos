"""Rule selection by ``contract.version`` (D-108 (2), D-109 (1), D-110; draft, not frozen).

``check_envelope_versioned`` reads ``contract.version`` and nothing else before
the schema step, then hands the envelope to the rule of that version:

* ``1.0.0`` -> ``contracts.check.check_envelope`` (the frozen 1.0.0 reference, unchanged);
* ``1.1.0`` -> ``contracts.ic00_v110.check_envelope``;
* any other string -> ``unsupported_contract_version`` (never checked with a
  newer rule by default; D-108 (2), D-110 (1));
* a missing/non-object ``contract`` or a ``version`` that is not a string cannot
  select a rule: ``schema`` (a structure error, not an unsupported version).

Parent/child versions (D-110 (2)): parent and child may carry different
versions. Each is checked with the rule of its own ``contract.version``. A parent's
``content_id`` is computed from the parent's own ``contract`` (``ids.content_id``
hashes the envelope as it is) and is never re-read under the child's version.

Two ways to supply the parents' ``content_id``:

* A, ``check_envelope_versioned(envelope, lookup)``: ``lookup`` maps
  artifact_id -> {content_id, seq, observation_id} of already-stored artifacts and
  is trusted (as in ``check.check_envelope``).
* B, ``check_envelope_with_parents(envelope, parent_envelopes, ancestor_lookup)``:
  the parents' envelopes themselves. Each parent is checked with its own version's
  rule (which recomputes its content_id and artifact_id from its own contract);
  the lookup for the child is then built from those verified parents.
  ``ancestor_lookup`` is the same shape as in A, for the parents' own parents.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from contracts import check, ic00_v110
from contracts.check import Violation
from contracts.ids import Lookup, content_id

RULES: dict[str, Callable[[Mapping[str, Any], Lookup], list[Violation]]] = {
    "1.0.0": check.check_envelope,
    ic00_v110.VERSION: ic00_v110.check_envelope,
}


def contract_version(envelope: Any) -> tuple[str | None, Violation | None]:
    """Read ``contract.version`` only. Returns (version, None) or (None, violation)."""
    contract = envelope.get("contract") if isinstance(envelope, Mapping) else None
    if not isinstance(contract, Mapping):
        return None, Violation("schema", "contract: missing or not an object (no rule can be selected)")
    version = contract.get("version")
    if not isinstance(version, str):
        return None, Violation("schema", "contract/version: missing or not a string (no rule can be selected)")
    if version not in RULES:
        return None, Violation(
            "unsupported_contract_version",
            f"contract.version {version!r} is not supported (supported: {sorted(RULES)})",
        )
    return version, None


def check_envelope_versioned(envelope: Mapping[str, Any], lookup: Lookup) -> list[Violation]:
    """A: select the rule by ``contract.version``; the parents' content_id come from ``lookup``."""
    version, violation = contract_version(envelope)
    if violation is not None or version is None:
        return [violation] if violation is not None else []
    return RULES[version](envelope, lookup)


def check_envelope_with_parents(
    envelope: Mapping[str, Any],
    parent_envelopes: Mapping[str, Mapping[str, Any]],
    ancestor_lookup: Lookup,
) -> list[Violation]:
    """B: check the parents with their own version's rule, then the child.

    ``parent_envelopes``: artifact_id -> the parent's envelope (every parent and the
    calibration artifact the child refers to). ``ancestor_lookup``: artifact_id ->
    {content_id, seq, observation_id} of the parents' own parents (empty for roots).
    Extra codes: ``parent_invalid`` (the parent fails its own version's rule; the
    message lists the codes), ``parent_key_mismatch`` (the key is not the parent's
    artifact_id). A parent that fails is left out of the child's lookup, so the
    child also reports ``parent_unknown`` for it.
    """
    version, violation = contract_version(envelope)
    if violation is not None or version is None:
        return [violation] if violation is not None else []
    out: list[Violation] = []
    lookup: dict[str, dict[str, Any]] = {}
    for key in sorted(parent_envelopes):
        parent = parent_envelopes[key]
        found = check_envelope_versioned(parent, ancestor_lookup)
        if found:
            codes = ",".join(sorted({v.code for v in found}))
            out.append(Violation("parent_invalid", f"{key}: {codes}"))
            continue
        if parent["artifact_id"] != key:
            out.append(Violation("parent_key_mismatch", key))
            continue
        lookup[key] = {
            "content_id": content_id(parent, ancestor_lookup),  # parent's own contract, as stored
            "observation_id": parent["observation_id"],
            "seq": parent["seq"],
        }
    out.extend(RULES[version](envelope, lookup))
    return out
