"""IC-02 payload checks that need more than the schema (design v0.7.1 3.3.2, 3.3.3).

S35 (series shape and key set), S36 (undefined only where the contract says),
S37 (last element equals ``metrics``; with no displacement interval, T = 1, the three displacement values are null / undefined), S38 (pair verdict recomputed), plus the
per-Blob checks of :mod:`contracts.blob`. ``stored`` maps artifact_id ->
``{"envelope": ...}`` for the calibration the payload points at; ``blobs`` maps
uri -> bytes. Series definitions and the undefined conditions are in
``msr/README.md``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from contracts.blob import INT64_MIN, check_blob, decode_int64
from contracts.check import Violation

_CONTENT_ID = re.compile(r"cnt:[0-9a-f]{64}")

# series name -> (metrics group, metrics key)
SERIES: dict[str, tuple[str, str]] = {
    "displacement_mean": ("displacement", "mean"),
    "displacement_median": ("displacement", "median"),
    "displacement_longest_sub_delta_run": ("displacement", "longest_sub_delta_run"),
    "recurrence_pair_fraction": ("recurrence", "pair_fraction"),
    "recurrence_return_count": ("recurrence", "return_count"),
    "recurrence_return_rate": ("recurrence", "return_rate"),
    "diversity_cell_entropy": ("diversity", "cell_entropy"),
    "diversity_participation_ratio": ("diversity", "participation_ratio"),
    "persistence_longest_stay": ("persistence", "longest_stay"),
    "persistence_dominant_cell_share": ("persistence", "dominant_cell_share"),
}


# Series the contract says may hold "no value"; each must always declare
# ``undefined: "int64_min"`` and no other series may (msr/README.md, 0.7.1).
CAN_BE_UNDEFINED: frozenset[str] = frozenset(SERIES)


def expected_undefined(
    name: str, length: int, thresholds: Mapping[str, Any], has_codebook: bool
) -> set[int]:
    """Positions ``t`` whose value is "undefined" by the contract (msr/README.md)."""
    everything = set(range(length))
    eps, delta, w_min = thresholds["epsilon"], thresholds["delta"], thresholds["w_min"]
    if name in ("displacement_mean", "displacement_median", "diversity_participation_ratio"):
        return {0}
    if name == "displacement_longest_sub_delta_run":
        return everything if delta is None else {0}
    if name == "recurrence_pair_fraction":
        if eps is None or w_min is None:
            return everything
        return set(range(min(length, w_min + 1)))
    if name in ("recurrence_return_count", "recurrence_return_rate"):
        return everything if eps is None or w_min is None else set()
    if name == "diversity_cell_entropy":
        return set() if has_codebook else everything
    return set() if has_codebook or eps is not None else everything  # persistence_*


def verdict_state(d: int, calibration: Mapping[str, Any] | None) -> str:
    """Section 3.3.3, on the payload's integers."""
    if calibration is None:
        return "UNCALIBRATED"
    lo, hi = calibration["values"]["noise_floor_lower"], calibration["values"]["noise_floor_upper"]
    if d < lo:
        return "STAGNANT"
    if d <= hi:
        return "NOISE_FLOOR_INTERNAL"
    return "STRUCTURAL_SHIFT_DETECTED"


def check_geometry(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any],
    blobs: Mapping[str, bytes],
) -> list[Violation]:
    payload = envelope["payload"]
    out: list[Violation] = []
    if payload["mode"] == "pair":
        ref = payload["calibration"]
        cal = None
        if ref is not None:
            entry = stored.get(ref["artifact_id"])
            if entry is None:
                return [Violation("calibration_unknown", ref["artifact_id"])]
            cal = entry["envelope"]["payload"]
        want = verdict_state(payload["distance"]["value"], cal)
        if payload["verdict"]["state"] != want:
            out.append(Violation("S38", f"verdict {payload['verdict']['state']} != {want}"))
        return out
    length = payload["input_ref"]["length"]
    has_codebook = any(p["role"] == "codebook" for p in envelope["parents"])
    for name, (group, key) in SERIES.items():
        ref = payload["series"][name]
        data = blobs.get(ref["uri"])
        for v in check_blob(ref, data):
            out.append(Violation(v.code, f"{name}: {v.message}"))
        declared = ref.get("undefined") == "int64_min"
        if declared != (name in CAN_BE_UNDEFINED):
            out.append(Violation("S36", f"{name}: undefined declaration must be {name in CAN_BE_UNDEFINED}"))
        if ref["shape"] != [length]:
            out.append(Violation("S35", f"{name}: shape {ref['shape']} != [{length}]"))
        if data is None or len(data) != 8 * length:
            continue
        values = decode_int64(data)
        want_undef = expected_undefined(name, len(values), payload["thresholds"], has_codebook)
        got_undef = {t for t, v in enumerate(values) if v == INT64_MIN}
        if got_undef != want_undef:
            out.append(Violation("S36", f"{name}: undefined at {sorted(got_undef)[:5]}, expected {sorted(want_undef)[:5]}"))
        metric = payload["metrics"][group][key]
        last = values[-1] if values else None
        if (INT64_MIN if metric is None else metric) != last:
            out.append(Violation("S37", f"{name}: last element {last} != metrics {metric}"))
    return out


def check_calibration_parents(
    envelope: Mapping[str, Any], parent_contents: Mapping[str, str]
) -> list[Violation]:
    """The parent-reference checks of ``msr/README.md`` (calibration).

    ``parent_contents`` is what nvs-runtime fetched from HEKB and confirmed
    (artifact_id -> content_id). Codes: ``parent_unknown``,
    ``parent_content_id_form`` (a content_id that is not ``cnt:`` + 64 hex),
    ``codebook_content_mismatch``, ``role_set_mismatch``, ``role_duplicate``,
    ``null_set_ordered``, ``codebook_ordered``, ``null_set_mismatch``.
    """
    payload = envelope["payload"]
    out: list[Violation] = []
    for artifact, content in parent_contents.items():
        if not isinstance(content, str) or not _CONTENT_ID.fullmatch(content):
            out.append(Violation("parent_content_id_form", artifact))
    names = [p["role"] for p in envelope["parents"]]
    roles = {p["role"]: p for p in reversed(envelope["parents"])}  # first of a repeated role wins
    if len(names) != len(roles):
        out.append(Violation("role_duplicate", "a role appears more than once in parents"))
    for parent in envelope["parents"]:
        for artifact in parent["artifact_ids"]:
            if artifact not in parent_contents:
                out.append(Violation("parent_unknown", artifact))
    codebook = payload["values"]["codebook_ref"]
    if codebook is not None and parent_contents.get(codebook["artifact_id"]) != codebook["content_id"]:
        out.append(Violation("codebook_content_mismatch", codebook["artifact_id"]))
    wanted = {"null_set"} | ({"codebook"} if codebook is not None else set())
    if set(roles) != wanted:
        out.append(Violation("role_set_mismatch", f"roles {sorted(roles)} != {sorted(wanted)}"))
    if "null_set" in roles:
        if roles["null_set"]["ordered"] is not False:
            out.append(Violation("null_set_ordered", "null_set must be ordered: false"))
        if roles["null_set"]["artifact_ids"] != payload["null_set"]:
            out.append(Violation("null_set_mismatch", "payload null_set differs from the parents' null_set"))
    if "codebook" in roles and roles["codebook"]["ordered"] is not False:
        out.append(Violation("codebook_ordered", "codebook must be ordered: false"))
    return out
