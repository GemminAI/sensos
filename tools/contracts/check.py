"""check_envelope: the part of the Integration Gate (section 5) decidable from
IC-00 alone: schema, id recomputation, producer/kind pairs (S4), array order
(S16), parents known (section 5 step 3), observation_id cases (S8), seq order (S5).
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any, NamedTuple

from jsonschema import Draft202012Validator

from contracts.errors import ContractError
from contracts.ids import Lookup, artifact_id, content_id, sorted_set
from contracts.schemas import validator

# Section 2.4 instantiated with producer names (the design names roles, not
# strings; see README.md). Prefix entries end with ":".
PRODUCER_KINDS: dict[str, frozenset[str]] = {
    "nvs-kernel": frozenset({"observation"}),  # NVS Edge
    "nvs-runtime": frozenset({"observation", "interpretation", "outcome"}),
    "hekb-vnext": frozenset({"observation"}),  # recall events only
    "hext": frozenset({"evidence"}),
    "meaning-mapper": frozenset({"interpretation"}),
    "meaning-space-runtime": frozenset({"interpretation"}),
    "categorical-lift-engine": frozenset({"interpretation"}),
    "sensos-ux": frozenset({"selection"}),  # HANKO
}
PRODUCER_PREFIXES: dict[str, frozenset[str]] = {
    "adapter:": frozenset({"interpretation"}),  # carry-evidence adapters
    "capability:": frozenset({"interpretation"}),  # capability declarations
}


class Violation(NamedTuple):
    code: str
    message: str


@lru_cache(maxsize=1)
def _envelope_validator() -> Draft202012Validator:
    return validator("common/artifact.schema.json")


def _allowed_kinds(name: str) -> frozenset[str]:
    if name in PRODUCER_KINDS:
        return PRODUCER_KINDS[name]
    for prefix, kinds in PRODUCER_PREFIXES.items():
        if name.startswith(prefix):
            return kinds
    return frozenset()


def _sorted_ok(items: list[Any], key: Any) -> bool:
    return items == sorted(items, key=key)


def _s16(envelope: Mapping[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    for name, fields in (("policy_refs", ("name", "sha256")), ("rule_refs", ("name", "version", "sha256"))):
        items = list(envelope[name])
        try:
            if items != sorted_set(items, fields, name):
                out.append(Violation("S16", f"{name} is not sorted"))
        except ContractError as exc:
            out.append(Violation("S16", exc.message))
    parents = list(envelope["parents"])
    roles = [p["role"] for p in parents]
    if len(set(roles)) != len(roles):
        out.append(Violation("S16", "duplicate role in parents"))
    if not _sorted_ok(roles, lambda r: r.encode("utf-8")):
        out.append(Violation("S16", "parents roles are not in name order"))
    for parent in parents:
        ids = list(parent["artifact_ids"])
        if not parent["ordered"]:
            if len(set(ids)) != len(ids):
                out.append(Violation("S16", f"duplicate ids in unordered role {parent['role']!r}"))
            if not _sorted_ok(ids, lambda a: a.encode("utf-8")):
                out.append(Violation("S16", f"ids of unordered role {parent['role']!r} not sorted"))
    return out


def _parent_ids(envelope: Mapping[str, Any]) -> list[str]:
    return [a for p in envelope["parents"] for a in p["artifact_ids"]]


def check_envelope(envelope: Mapping[str, Any], lookup: Lookup) -> list[Violation]:
    """Return all violations found (empty list = accepted).

    ``lookup`` maps artifact_id to the stored envelope (at least ``content_id``,
    ``seq``, ``observation_id``) of every already-saved artifact.
    """
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
        stored = lookup.get(calibration["artifact_id"])
        if stored is None:
            out.append(Violation("calibration_unknown", calibration["artifact_id"]))
        elif stored.get("content_id") != calibration["content_id"]:
            out.append(Violation("calibration_mismatch", calibration["artifact_id"]))

    if not unknown and not any("duplicate" in v.message for v in s16):
        try:
            if content_id(envelope, lookup) != envelope["content_id"]:
                out.append(Violation("content_id_mismatch", "recomputed content_id differs"))
            if artifact_id(envelope, lookup) != envelope["artifact_id"]:
                out.append(Violation("artifact_id_mismatch", "recomputed artifact_id differs"))
        except ContractError as exc:  # missing content_id in a lookup entry
            out.append(Violation("lookup_incomplete", exc.message))

    known = [lookup[a] for a in parent_ids if a in lookup]
    out.extend(_s8(envelope, known))
    out.extend(_s5(envelope, known, calibration, lookup))
    return out


def _s8(envelope: Mapping[str, Any], parents: list[Mapping[str, Any]]) -> list[Violation]:
    own = envelope["observation_id"]
    if not envelope["parents"]:
        if envelope["kind"] == "observation" and own is None:
            return [Violation("S8", "a root observation needs an observation_id")]
        return []
    seen = {p.get("observation_id") for p in parents} - {None}
    if len(seen) == 1:
        if own not in seen:
            return [Violation("S8", "derived artifact must inherit the parents' observation_id")]
    elif own is not None:
        return [Violation("S8", "observation_id must be null (parents span 0 or several observations)")]
    return []


def _s5(
    envelope: Mapping[str, Any],
    parents: list[Mapping[str, Any]],
    calibration: Mapping[str, Any] | None,
    lookup: Lookup,
) -> list[Violation]:
    refs = list(parents)
    if calibration is not None and calibration["artifact_id"] in lookup:
        refs.append(lookup[calibration["artifact_id"]])
    out = []
    for ref in refs:
        seq = ref.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool):
            out.append(Violation("lookup_incomplete", "stored artifact has no integer seq"))
        elif seq >= envelope["seq"]:
            out.append(Violation("S5", f"parent seq {seq} is not before seq {envelope['seq']}"))
    return out
