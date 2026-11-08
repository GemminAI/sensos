"""IC-02 0.9.0 / 0.10.0: the window (D-129 first 128 rows; D-132 position and length) -- checks that a schema cannot express.

Two payloads are involved (``msr/README.md``, "window"):

* ``msr.trajectory-window`` 0.9.0 -- the window as its own artifact. ``check_window``.
* ``msr.geometry-measurement`` 0.9.0, ``mode: single`` -- ``input_scope`` says whether
  the measured input is a ``full`` trajectory or this ``window``. ``check_scope``.

Two versions are read, each under its own rule (never one as the other):

* 0.9.0 (``msr/archive/0.9.0``): fixed start 0, length 128, rule ``prefix_rows`` (the constants below).
* 0.10.0 (D-132): ``window.rule`` is ``prefix_rows`` (start 0) or ``rows`` (start >= 0, length >= 1); the window's
  start and length are read from the payload. Positions (head, middle, tail ...) are not narrowed by the contract.
  Extra codes for 0.10.0 only: ``window_range``, ``window_token_range``, ``window_space_position``,
  ``pair_window_length``.

Codes (named, not S-numbers; the schema step reports ``schema`` alone, as everywhere):

======================= ===========================================================
``window_kind``         kind is not ``observation``
``window_producer``     producer is not ``nvs-runtime``
``window_space``        envelope ``space_id`` is null (a window is measured in a space)
``window_parents``      parents are not exactly one role ``source_trajectory`` (one
                        artifact, ``ordered: false``)
``window_policy``       ``policy.sha256`` is not the sha256 of ``policy.name``
``window_shape``        a Blob's ``shape`` or byte length is not the window's length in rows
                        (``[length, dimension]`` / ``[length]``; 128 in 0.9.0), or ``token_index``
                        is not strictly increasing
``window_sha256``       ``window.content_sha256`` differs from ``points.sha256``, or a
                        Blob's bytes differ from its ``sha256`` / ``uri``
``window_nonfinite``    a NaN or an infinity among the points
``window_origin``       the stored parent says otherwise (trajectory_id, length, position)
``window_origin_unreadable`` the stored parent lacks the fields read from it
``parent_unknown``      the referenced parent is not in ``stored``
``window_range``        (0.10.0) ``start + length`` exceeds ``origin.length`` (the window leaves the original)
``window_token_range``  (0.10.0) a ``token_index`` entry is outside ``[0, origin.length)`` (D-133 (1): outside
                        [0, origin.length) is rejected)
``window_space_position`` (0.10.0) another stored window in the same ``space_id`` has a different ``start`` or ``length``
                        (D-132 (4), D-133 (4): the space is separated by position; (start, length) are compared)
``pair_window_length``  (0.10.0 pair) the two window parents have different lengths: ``equal_only`` cannot compare them
                        (``common_prefix`` is not adopted, D-120)
``window_length``       (measurement) ``input_ref.length`` is not the scope's length
``window_parent``       (measurement) ``parents`` has no single role ``trajectory``
``window_not_window``   (measurement) scope says ``window`` but the parent is no window
``window_undeclared``   (measurement) scope says ``full`` but the parent is a window
``full_length_mismatch`` (measurement) scope says ``full`` but ``input_ref.length`` is not the
                        stored parent's ``length`` (a prefix measured without saying so)
``window_mismatch``     (measurement) the window parent differs from the scope or from
                        the measurement's own fields (0.10.0: also ``rule``)
======================= ===========================================================

A reader that holds the original RAW rows can additionally check that the window
is really their rows ``[start, start + length)`` (``prefix_matches`` for the 0.9.0 first 128, ``rows_match`` for any start);
the Gate cannot, because the RAW rows are held by reference, not in the artifact (README).
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Mapping, Sequence
from typing import Any

from contracts.check import Violation

WINDOW_RULE = "prefix_rows"
ROWS_RULE = "rows"
V090 = "0.9.0"
V0100 = "0.10.0"
WINDOW_START = 0
WINDOW_LENGTH = 128
WINDOW_POLICY = "first-128-rows/1"
SOURCE_ROLE = "source_trajectory"
WINDOW_SCHEMA = "msr.trajectory-window"
WINDOW_PRODUCER = "nvs-runtime"
WINDOW_KIND = "observation"


def _one_parent(envelope: Mapping[str, Any], role: str) -> str | None:
    """The single artifact_id of the only parent entry with this role, else None."""
    entries = [p for p in envelope["parents"] if p["role"] == role]
    if len(entries) != 1 or len(envelope["parents"]) != 1 or len(entries[0]["artifact_ids"]) != 1:
        return None
    return entries[0]["artifact_ids"][0]  # type: ignore[no-any-return]


def _params(envelope: Mapping[str, Any]) -> tuple[str, int, int]:
    """(rule, start, length) the window declares. 0.9.0 is the fixed first-128-rows window; 0.10.0 reads the payload."""
    if envelope["payload_schema"]["version"] == V090:
        return WINDOW_RULE, WINDOW_START, WINDOW_LENGTH
    w = envelope["payload"]["window"]
    return w["rule"], w["start"], w["length"]


def check_window(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any],
    blobs: Mapping[str, bytes],
) -> list[Violation]:
    """``envelope`` has passed the payload schema. ``stored``: artifact_id -> ``{"envelope": ...}``."""
    p = envelope["payload"]
    _rule, start, L = _params(envelope)
    out: list[Violation] = []
    if envelope["kind"] != WINDOW_KIND:
        out.append(Violation("window_kind", f"kind {envelope['kind']!r} (a window is an {WINDOW_KIND})"))
    if envelope["producer"]["name"] != WINDOW_PRODUCER:
        out.append(Violation("window_producer", f"producer {envelope['producer']['name']!r} (expected {WINDOW_PRODUCER!r})"))
    if envelope["space_id"] is None:
        out.append(Violation("window_space", "space_id is null"))
    parent = _one_parent(envelope, SOURCE_ROLE)
    entry = next((e for e in envelope["parents"] if e["role"] == SOURCE_ROLE), None)
    if parent is None or entry is None or entry["ordered"] is not False:
        out.append(Violation("window_parents", f"parents must be exactly one role {SOURCE_ROLE!r}, one artifact, ordered false"))
    if p["policy"]["sha256"] != hashlib.sha256(p["policy"]["name"].encode("utf-8")).hexdigest():
        out.append(Violation("window_policy", "policy.sha256 is not the sha256 of policy.name"))

    points, tix = p["points"], p["token_index"]
    if points["shape"] != [L, p["dimension"]]:
        out.append(Violation("window_shape", f"points.shape {points['shape']} != [{L}, {p['dimension']}]"))
    if p["window"]["content_sha256"] != points["sha256"]:
        out.append(Violation("window_sha256", "window.content_sha256 differs from points.sha256"))
    for name, ref in (("points", points), ("token_index", tix)):
        if ref["uri"] != "blob:sha256:" + ref["sha256"]:
            out.append(Violation("window_sha256", f"{name}.uri hex differs from sha256"))
    data = blobs.get(points["uri"])
    if data is not None:
        if hashlib.sha256(data).hexdigest() != points["sha256"]:
            out.append(Violation("window_sha256", "points bytes differ from points.sha256 (the window's content)"))
        if len(data) != L * p["dimension"] * 4:
            out.append(Violation("window_shape", f"points has {len(data)} bytes, not {L} x {p['dimension']} x 4"))
        else:
            values = struct.unpack(f"<{len(data) // 4}f", data)
            if not all(math.isfinite(v) for v in values):
                out.append(Violation("window_nonfinite", "a NaN or infinity among the points"))
    raw = blobs.get(tix["uri"])
    if raw is not None:
        if hashlib.sha256(raw).hexdigest() != tix["sha256"]:
            out.append(Violation("window_sha256", "token_index bytes differ from token_index.sha256"))
        if len(raw) != 8 * L:
            out.append(Violation("window_shape", f"token_index has {len(raw)} bytes, not {8 * L}"))
        else:
            ti = struct.unpack(f"<{L}q", raw)
            if any(b <= a for a, b in zip(ti, ti[1:], strict=False)):
                out.append(Violation("window_shape", "token_index is not strictly increasing"))

    if parent is not None:
        held = stored.get(parent)
        if held is None:
            out.append(Violation("parent_unknown", parent))
        else:
            out.extend(_origin_agrees(p["origin"], held["envelope"]["payload"]))
    if envelope["payload_schema"]["version"] == V0100:
        out.extend(_check_rows_range(envelope, stored, raw, start, L))
    return out


def _check_rows_range(envelope: Mapping[str, Any], stored: Mapping[str, Any], token_blob: bytes | None, start: int, length: int) -> list[Violation]:
    """0.10.0 only (D-132): the window lies inside the original; token_index range; one position per space."""
    p = envelope["payload"]
    out: list[Violation] = []
    origin_length = p["origin"]["length"]
    if start + length > origin_length:
        out.append(Violation("window_range", f"start {start} + length {length} = {start + length} > origin.length {origin_length}"))
    if token_blob is not None and len(token_blob) == 8 * length:
        ti = struct.unpack(f"<{length}q", token_blob)
        if min(ti) < 0 or max(ti) >= origin_length:
            out.append(Violation("window_token_range", f"token_index [{min(ti)}, {max(ti)}] is outside [0, {origin_length})"))
    for aid, held in stored.items():
        other = held["envelope"]
        if aid == envelope.get("artifact_id") or other.get("payload_schema", {}).get("id") != WINDOW_SCHEMA:
            continue
        if other.get("space_id") != envelope["space_id"] or envelope["space_id"] is None:
            continue
        _r, o_start, o_length = _params(other)
        if (o_start, o_length) != (start, length):
            out.append(Violation("window_space_position", f"space_id is shared with {aid}, which has start {o_start} length {o_length}"))
            break
    return out


def _origin_agrees(origin: Mapping[str, Any], held: Any) -> list[Violation]:
    """The stored source trajectory must say what ``origin`` says.

    Fields read from it (the draft ``nvs.hidden-trajectory`` 0.1.0 names): ``raw_ref.trajectory_id``,
    ``length``, ``position``. Nothing else is read.
    """
    try:
        got = {"trajectory_id": held["raw_ref"]["trajectory_id"], "length": held["length"], "position": held["position"]}
    except (KeyError, TypeError):
        return [Violation("window_origin_unreadable", "the stored parent has no raw_ref.trajectory_id / length / position")]
    bad = [k for k in ("trajectory_id", "length", "position") if got[k] != origin[k]]
    return [Violation("window_origin", f"{k}: stored {got[k]!r} != window origin {origin[k]!r}") for k in bad]


def check_scope(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any],
) -> list[Violation]:
    """``input_scope`` of a 0.9.0 / 0.10.0 ``single`` measurement against its ``trajectory`` parent."""
    p = envelope["payload"]
    scope = p["input_scope"]
    parent = _one_parent_role(envelope["parents"], "trajectory")
    out: list[Violation] = []
    held = stored.get(parent) if parent is not None else None
    held_env = held["envelope"] if held is not None else None
    is_window = held_env is not None and held_env["payload_schema"]["id"] == WINDOW_SCHEMA
    if scope["kind"] == "full":
        if is_window:
            out.append(Violation("window_undeclared", "the trajectory parent is a window but input_scope says full"))
        elif held_env is not None:
            length = held_env["payload"].get("length") if isinstance(held_env["payload"], Mapping) else None
            if type(length) is int and length != p["input_ref"]["length"]:
                out.append(Violation("full_length_mismatch", f"input_ref.length {p['input_ref']['length']} != the whole trajectory's length {length}"))
        return out
    if scope["length"] != p["input_ref"]["length"]:
        out.append(Violation("window_length", f"input_ref.length {p['input_ref']['length']} != scope length {scope['length']}"))
    if parent is None:
        out.append(Violation("window_parent", "parents must have exactly one artifact under the role 'trajectory'"))
        return out
    if held_env is None:
        out.append(Violation("parent_unknown", parent))
        return out
    if not is_window:
        out.append(Violation("window_not_window", f"scope is window but the parent is {held_env['payload_schema']['id']!r}"))
        return out
    w = held_env["payload"]
    same = {
        "source_trajectory_id": w["origin"]["trajectory_id"] == scope["source_trajectory_id"],
        "content_sha256": w["window"]["content_sha256"] == scope["content_sha256"],
        "length": w["window"]["length"] == scope["length"],
        "start": w["window"]["start"] == scope["start"],
        "dimension": w["dimension"] == p["input_ref"]["dimension"],
        "model_build_id": w["model_build_id"] == p["input_ref"]["model_build_id"],
        "policy": w["policy"] == p["input_ref"]["policy"],
        "layer": w["layer"] == p["layer"],
        "source": w["source"] == p["source"],
        "space_id": held_env["space_id"] == p["space_id"],
    }
    if envelope["payload_schema"]["version"] == V0100:
        same["rule"] = w["window"]["rule"] == scope["rule"]  # 0.9.0: the schema fixes the rule, so there is nothing to compare
    out.extend(Violation("window_mismatch", f"{k} differs between the window and the measurement") for k, ok in same.items() if not ok)
    return out


def _one_parent_role(parents: Sequence[Mapping[str, Any]], role: str) -> str | None:
    entries = [e for e in parents if e["role"] == role]
    if len(entries) != 1 or len(entries[0]["artifact_ids"]) != 1:
        return None
    return entries[0]["artifact_ids"][0]  # type: ignore[no-any-return]


def check_pair_windows(envelope: Mapping[str, Any], stored: Mapping[str, Any]) -> list[Violation]:
    """0.10.0 ``pair``: if both parents (roles ``left`` and ``right``) are stored windows, their lengths must be equal.

    ``equal_only`` is the only alignment adopted; ``common_prefix`` is not (D-120), so windows of different lengths
    cannot be compared. Parents that are not stored windows are not judged here (as in 0.9.0)."""
    lengths = []
    for role in ("left", "right"):
        aid = _one_parent_role(envelope["parents"], role)
        held = stored.get(aid) if aid is not None else None
        if held is not None and held["envelope"]["payload_schema"]["id"] == WINDOW_SCHEMA:
            lengths.append(_params(held["envelope"])[2])
    if len(lengths) == 2 and lengths[0] != lengths[1]:
        return [Violation("pair_window_length", f"window lengths {lengths[0]} != {lengths[1]}: equal_only cannot compare them (no common_prefix, D-120)")]
    return []


def rows_match(window_points: bytes, source_rows: bytes, dimension: int, start: int, length: int) -> bool:
    """For a reader that holds the RAW rows (float32 LE, row-major): is the window their rows ``[start, start + length)``?"""
    a = start * dimension * 4
    return len(source_rows) >= a + length * dimension * 4 and window_points == source_rows[a : a + length * dimension * 4]


def prefix_matches(window_points: bytes, source_rows: bytes, dimension: int) -> bool:
    """For a reader that holds the RAW rows (float32 LE, row-major): is the window their first 128 rows?"""
    return window_points == source_rows[: WINDOW_LENGTH * dimension * 4]
