"""IC-02 0.9.0: the first-128-rows window (D-129) -- checks that a schema cannot express.

Two payloads are involved (``msr/README.md``, "window"):

* ``msr.trajectory-window`` 0.9.0 -- the window as its own artifact. ``check_window``.
* ``msr.geometry-measurement`` 0.9.0, ``mode: single`` -- ``input_scope`` says whether
  the measured input is a ``full`` trajectory or this ``window``. ``check_scope``.

Fixed in this implementation (single place; the schemas carry the same constants):
start 0, length 128, rule ``prefix_rows``, policy name ``first-128-rows/1``.
Position and length as parameters are a future extension (README), not here.

Codes (named, not S-numbers; the schema step reports ``schema`` alone, as everywhere):

======================= ===========================================================
``window_kind``         kind is not ``observation``
``window_producer``     producer is not ``nvs-runtime``
``window_space``        envelope ``space_id`` is null (a window is measured in a space)
``window_parents``      parents are not exactly one role ``source_trajectory`` (one
                        artifact, ``ordered: false``)
``window_policy``       ``policy.sha256`` is not the sha256 of ``policy.name``
``window_shape``        a Blob's ``shape`` or byte length is not 128 rows
                        (``[128, dimension]`` / ``[128]``), or ``token_index`` is not
                        strictly increasing
``window_sha256``       ``window.content_sha256`` differs from ``points.sha256``, or a
                        Blob's bytes differ from its ``sha256`` / ``uri``
``window_nonfinite``    a NaN or an infinity among the points
``window_origin``       the stored parent says otherwise (trajectory_id, length, position)
``window_origin_unreadable`` the stored parent lacks the fields read from it
``parent_unknown``      the referenced parent is not in ``stored``
``window_length``       (measurement) ``input_ref.length`` is not the scope's length
``window_parent``       (measurement) ``parents`` has no single role ``trajectory``
``window_not_window``   (measurement) scope says ``window`` but the parent is no window
``window_undeclared``   (measurement) scope says ``full`` but the parent is a window
``full_length_mismatch`` (measurement) scope says ``full`` but ``input_ref.length`` is not the
                        stored parent's ``length`` (a prefix measured without saying so)
``window_mismatch``     (measurement) the window parent differs from the scope or from
                        the measurement's own fields
======================= ===========================================================

A reader that holds the original RAW rows can additionally check that the window
is really their first 128 rows (``prefix_matches``); the Gate cannot, because the
RAW rows are held by reference, not in the artifact (README).
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Mapping, Sequence
from typing import Any

from contracts.check import Violation

WINDOW_RULE = "prefix_rows"
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


def check_window(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any],
    blobs: Mapping[str, bytes],
) -> list[Violation]:
    """``envelope`` has passed the payload schema. ``stored``: artifact_id -> ``{"envelope": ...}``."""
    p = envelope["payload"]
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
    if points["shape"] != [WINDOW_LENGTH, p["dimension"]]:
        out.append(Violation("window_shape", f"points.shape {points['shape']} != [{WINDOW_LENGTH}, {p['dimension']}]"))
    if p["window"]["content_sha256"] != points["sha256"]:
        out.append(Violation("window_sha256", "window.content_sha256 differs from points.sha256"))
    for name, ref in (("points", points), ("token_index", tix)):
        if ref["uri"] != "blob:sha256:" + ref["sha256"]:
            out.append(Violation("window_sha256", f"{name}.uri hex differs from sha256"))
    data = blobs.get(points["uri"])
    if data is not None:
        if hashlib.sha256(data).hexdigest() != points["sha256"]:
            out.append(Violation("window_sha256", "points bytes differ from points.sha256 (the window's content)"))
        if len(data) != WINDOW_LENGTH * p["dimension"] * 4:
            out.append(Violation("window_shape", f"points has {len(data)} bytes, not {WINDOW_LENGTH} x {p['dimension']} x 4"))
        else:
            values = struct.unpack(f"<{len(data) // 4}f", data)
            if not all(math.isfinite(v) for v in values):
                out.append(Violation("window_nonfinite", "a NaN or infinity among the points"))
    raw = blobs.get(tix["uri"])
    if raw is not None:
        if hashlib.sha256(raw).hexdigest() != tix["sha256"]:
            out.append(Violation("window_sha256", "token_index bytes differ from token_index.sha256"))
        if len(raw) != 8 * WINDOW_LENGTH:
            out.append(Violation("window_shape", f"token_index has {len(raw)} bytes, not {8 * WINDOW_LENGTH}"))
        else:
            ti = struct.unpack(f"<{WINDOW_LENGTH}q", raw)
            if any(b <= a for a, b in zip(ti, ti[1:], strict=False)):
                out.append(Violation("window_shape", "token_index is not strictly increasing"))

    if parent is not None:
        held = stored.get(parent)
        if held is None:
            out.append(Violation("parent_unknown", parent))
        else:
            out.extend(_origin_agrees(p["origin"], held["envelope"]["payload"]))
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
    """``input_scope`` of a 0.9.0 ``single`` measurement against its ``trajectory`` parent."""
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
    out.extend(Violation("window_mismatch", f"{k} differs between the window and the measurement") for k, ok in same.items() if not ok)
    return out


def _one_parent_role(parents: Sequence[Mapping[str, Any]], role: str) -> str | None:
    entries = [e for e in parents if e["role"] == role]
    if len(entries) != 1 or len(entries[0]["artifact_ids"]) != 1:
        return None
    return entries[0]["artifact_ids"][0]  # type: ignore[no-any-return]


def prefix_matches(window_points: bytes, source_rows: bytes, dimension: int) -> bool:
    """For a reader that holds the RAW rows (float32 LE, row-major): is the window their first 128 rows?"""
    return window_points == source_rows[: WINDOW_LENGTH * dimension * 4]
