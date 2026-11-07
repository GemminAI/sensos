"""IC-00 1.1.0 envelope check (design v0.7.2 section 2.4, D-107, D-108; draft, not frozen).

The 1.1.0 rule is the 1.0.0 rule (``check.check_envelope``, unchanged and still
the 1.0.0 reference) with two differences:

* the schema is ``IC-00/1.1.0/artifact.schema.json`` (``contract.version`` is ``1.1.0``);
* the ``producer.name`` registry has two more entries, ``sensos-connector`` and
  ``sensos-inference`` (observation only, D-108 (1)(2)).

The registry is written out in full (not derived from ``check.PRODUCER_KINDS``)
so that this module reads as one specification. Everything after the schema
step is the same sequence as ``check.check_envelope``; the step functions
(S16, S8, S5, parent ids) are the 1.0.0 ones, which this rule does not change.

NOT implemented here (D-108 (3)): the payload restriction of ``sensos-connector``
(design section 2.4: "external request records and Record reports only", S28
onwards). It needs the IC-06 payload schemas.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from contracts.check import Violation, _parent_ids, _s5, _s16
from contracts.errors import ContractError
from contracts.ids import Lookup, artifact_id, content_id
from contracts.schemas import load_schema, validator

VERSION = "1.1.0"
SCHEMA_PATH = "IC-00/1.1.0/artifact.schema.json"

# D-116 (1): the IC-00 content_id form is the existing schema rule (common/provenance.schema.json $defs.contentId,
# the same pattern as the envelope's content_id); no new expression is written here. jsonschema applies it with re.search.
_CONTENT_ID_FORM = re.compile(load_schema("common/provenance.schema.json")["$defs"]["contentId"]["pattern"])


def _valid_stored_content_id(value: Any) -> bool:
    return isinstance(value, str) and _CONTENT_ID_FORM.search(value) is not None


PRODUCER_KINDS: dict[str, frozenset[str]] = {
    "nvs-kernel": frozenset({"observation"}),
    "nvs-runtime": frozenset({"observation", "interpretation", "outcome"}),
    "hekb-vnext": frozenset({"observation"}),
    "hext": frozenset({"evidence"}),
    "meaning-mapper": frozenset({"interpretation"}),
    "meaning-space-runtime": frozenset({"interpretation"}),
    "categorical-lift-engine": frozenset({"interpretation"}),
    "sensos-ux": frozenset({"selection"}),
    "sensos-connector": frozenset({"observation"}),  # new in 1.1.0 (D-108 (2))
    "sensos-inference": frozenset({"observation"}),  # new in 1.1.0 (D-101, D-108 (1))
}
PRODUCER_PREFIXES: dict[str, frozenset[str]] = {
    "adapter:": frozenset({"interpretation"}),
    "capability:": frozenset({"interpretation"}),
}


@lru_cache(maxsize=1)
def _envelope_validator() -> Draft202012Validator:
    return validator(SCHEMA_PATH)


def _allowed_kinds(name: str) -> frozenset[str]:
    if name in PRODUCER_KINDS:
        return PRODUCER_KINDS[name]
    for prefix, kinds in PRODUCER_PREFIXES.items():
        if name.startswith(prefix):
            return kinds
    return frozenset()


def check_envelope(envelope: Mapping[str, Any], lookup: Lookup) -> list[Violation]:
    """The 1.1.0 rule. ``lookup`` is the same as for ``check.check_envelope``."""
    errors = sorted(_envelope_validator().iter_errors(envelope), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        return [Violation("schema", f"{'/'.join(str(p) for p in first.absolute_path)}: {first.message}")]

    out: list[Violation] = []
    name, kind = envelope["producer"]["name"], envelope["kind"]
    if kind not in _allowed_kinds(name):
        out.append(Violation("S4", f"producer {name!r} may not produce kind {kind!r}"))
    s16 = _s16(envelope)
    out.extend(s16)

    parent_ids = _parent_ids(envelope)
    unknown = [a for a in parent_ids if a not in lookup]
    for a in unknown:
        out.append(Violation("parent_unknown", a))
    calibration = envelope["calibration_ref"]
    if calibration is not None:
        # D-114 (1): three separate states. (1.0.0 reports an entry without content_id as a mismatch.)
        stored = lookup.get(calibration["artifact_id"])
        if stored is None:
            out.append(Violation("calibration_unknown", calibration["artifact_id"]))
        elif not _valid_stored_content_id(stored.get("content_id")):
            # D-115/D-116 (1): the stored content_id must exist as a string of the IC-00 content_id form
            # (a missing key, null, a non-str type or a malformed string is incomplete).
            out.append(Violation("lookup_incomplete", f"calibration {calibration['artifact_id']}: stored content_id is missing or malformed"))
        elif stored["content_id"] != calibration["content_id"]:
            out.append(Violation("calibration_mismatch", calibration["artifact_id"]))

    if not unknown and not any("duplicate" in v.message for v in s16):
        try:
            if content_id(envelope, lookup) != envelope["content_id"]:
                out.append(Violation("content_id_mismatch", "recomputed content_id differs"))
            if artifact_id(envelope, lookup) != envelope["artifact_id"]:
                out.append(Violation("artifact_id_mismatch", "recomputed artifact_id differs"))
        except ContractError as exc:
            out.append(Violation("lookup_incomplete", exc.message))

    known = [lookup[a] for a in parent_ids if a in lookup]
    out.extend(_s8(envelope, known))
    out.extend(_s5(envelope, known, calibration, lookup))
    return out


def _s8(envelope: Mapping[str, Any], parents: list[Mapping[str, Any]]) -> list[Violation]:
    """S8 for 1.1.0 (D-116 (2), D-117). Same decisions as ``check._s8`` (1.0.0, frozen, untouched).

    The parents' ``observation_id`` values other than None (key missing or null) are counted as kinds by
    equality, not by hash, so a list or a dict does not raise. The type and the form are not checked (D-116 (7)
    leaves that open). Equality is Python's ``==``, so ``1`` and ``True`` are one kind, as in the set that
    ``check._s8`` builds.
    """
    own = envelope["observation_id"]
    if not envelope["parents"]:
        if envelope["kind"] == "observation" and own is None:
            return [Violation("S8", "a root observation needs an observation_id")]
        return []
    seen: list[Any] = []
    for p in parents:
        value = p.get("observation_id")
        if value is not None and not any(value == s for s in seen):
            seen.append(value)
    if len(seen) == 1:
        if not own == seen[0]:
            return [Violation("S8", "derived artifact must inherit the parents' observation_id")]
    elif own is not None:
        return [Violation("S8", "observation_id must be null (parents span 0 or several observations)")]
    return []
