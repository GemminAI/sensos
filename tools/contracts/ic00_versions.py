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
from contracts.check import Violation, _parent_ids
from contracts.errors import ContractError
from contracts.ids import Lookup, artifact_id, content_id

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


def _schema_violations(version: str, envelope: Mapping[str, Any]) -> list[Violation] | None:
    """Step 1 of B for the child: the schema of its own version. None = passes (D-111 (2) (1))."""
    validator = check._envelope_validator() if version == "1.0.0" else ic00_v110._envelope_validator()
    errors = sorted(validator.iter_errors(envelope), key=lambda e: list(e.absolute_path))
    if not errors:
        return None
    first = errors[0]
    return [Violation("schema", f"{'/'.join(str(p) for p in first.absolute_path)}: {first.message}")]


def check_envelope_with_parents(
    envelope: Mapping[str, Any],
    parent_envelopes: Mapping[str, Mapping[str, Any]],
    ancestor_lookup: Lookup,
) -> list[Violation]:
    """B (D-110 (2), D-111, D-112): check the parents with their own version's rule, then the child.

    ``parent_envelopes``: artifact_id -> the parent's envelope. ``ancestor_lookup``: artifact_id ->
    {content_id, seq, observation_id} of the parents' own parents (empty for roots).

    Order (D-111 (2), D-112 (2)(3)):

    1. version and schema of the child. Any code here is returned alone.
    2. the parents. Every entry of ``parent_envelopes`` is checked, also an entry the child does
       not refer to (D-112 (4)). Codes: ``parent_invalid`` (the parent fails its own version's rule,
       an unsupported version included; the message lists the codes), ``parent_key_mismatch`` (the key
       is not the artifact_id the parent's envelope computes), ``parent_unknown`` (a parent of the
       entry is not in ``ancestor_lookup``, or the artifact_id computed by no entry equals a
       reference of the child; D-112 (1)). Any code here is returned alone.
    3. the child (S4, S16, S5, S8, the recomputed ids, ...), with the parents' content_id
       recomputed from each parent's own contract.

    Not specified (D-112; the behaviour here is not frozen): the code when a parent's artifact_id
    cannot be computed (here: no key and no reference code of its own, its missing parents are
    reported as ``parent_unknown``); an ``ancestor_lookup`` entry with missing fields; where the
    child's ``calibration_ref`` is looked up (here: the parents' envelopes only); whether
    ``calibration_unknown`` for a parent uses ``ancestor_lookup`` (here: it does, through the
    parent's own check).
    """
    version, violation = contract_version(envelope)
    if violation is not None or version is None:
        return [violation] if violation is not None else []
    if (schema := _schema_violations(version, envelope)) is not None:
        return schema

    out: list[Violation] = []
    lookup: dict[str, dict[str, Any]] = {}
    computed_ids: set[str] = set()
    for key in sorted(parent_envelopes):
        parent = parent_envelopes[key]
        found = check_envelope_versioned(parent, ancestor_lookup)
        if found:
            codes = ",".join(sorted({v.code for v in found}))
            out.append(Violation("parent_invalid", f"{key}: {codes}"))
            for v in found:
                if v.code == "parent_unknown":
                    out.append(Violation("parent_unknown", f"{key}: {v.message}"))
        try:
            computed = artifact_id(parent, ancestor_lookup)
            parent_cid = content_id(parent, ancestor_lookup)  # the parent's own contract, as stored
        except (ContractError, KeyError, TypeError):
            continue
        computed_ids.add(computed)
        if computed != key:
            out.append(Violation("parent_key_mismatch", key))
        if not found:
            lookup[computed] = {
                "content_id": parent_cid,
                "observation_id": parent["observation_id"],
                "seq": parent["seq"],
            }
    for a in _parent_ids(envelope):
        if a not in computed_ids:
            out.append(Violation("parent_unknown", a))
    if out:
        return out
    return RULES[version](envelope, lookup)
