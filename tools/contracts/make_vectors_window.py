"""Generate the IC-02 0.9.0 window vectors (docs/architecture/contracts/msr/vectors/window.json).

Run:  python tools/contracts/make_vectors_window.py  (from the repository root)

Separate from ``make_vectors.py`` (1.0.0 / IC-02 0.7.1-0.8.0 vectors, never re-run for them) and
from ``make_vectors_v110.py``. It imports only their builders (``_env``, ``seal``, ``_stored``,
``_series_payload``).

Every expected code below is written by hand from the rules in ``msr/README.md`` ("window"), not taken
from the implementation under test. The generator then runs the implementation and refuses to write the
file if one case disagrees with its hand-written expectation.

One case = one envelope plus what the Gate would hold for it:
``stored`` (artifact_id -> {"envelope"}), ``lookup`` (artifact_id -> {content_id, seq, observation_id}),
and the shared ``blobs`` table (uri -> hex). ``expect.ic00`` = ``check_envelope_versioned(envelope, lookup)``;
``expect.payload`` = ``check_payload(envelope, stored, blobs)``. Accept = both empty.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts import ids  # noqa: E402
from contracts.gate import check_payload  # noqa: E402
from contracts.ic00_versions import check_envelope_versioned  # noqa: E402
from contracts.ic02 import SERIES  # noqa: E402
from contracts.make_vectors import SHA, _env, _series_payload, _stored, seal  # noqa: E402
from contracts.quantize import INT64_RANGE  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs/architecture/contracts/msr/vectors/window.json"
U = INT64_RANGE[0]
L = 128
D = 3
SES = ids.session_id_experiment("sha256:" + "c" * 64, "item-001", "baseline", 0, 7)
OBS = ids.observation_id(SES, 0)
BLOBS: dict[str, bytes] = {}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def blob(data: bytes) -> str:
    BLOBS["blob:sha256:" + sha(data)] = data
    return "blob:sha256:" + sha(data)


def rows(n: int = L, d: int = D, offset: float = 0.0) -> bytes:
    return b"".join(struct.pack("<f", offset + i * 0.5 + j * 0.25) for i in range(n) for j in range(d))


def ints(values: list[int]) -> bytes:
    return struct.pack(f"<{len(values)}q", *values)


def points_ref(data: bytes, n: int = L, d: int = D) -> dict[str, Any]:
    blob(data)
    return {"uri": "blob:sha256:" + sha(data), "sha256": sha(data), "media_type": "application/vnd.sensos.ndarray-raw",
            "dtype": "float32", "shape": [n, d], "byte_order": "little", "order": "C", "unit": "activation"}


def index_ref(values: list[int]) -> dict[str, Any]:
    data = ints(values)
    blob(data)
    return {"uri": "blob:sha256:" + sha(data), "sha256": sha(data), "media_type": "application/vnd.sensos.ndarray-raw",
            "dtype": "int64", "shape": [len(values)], "byte_order": "little", "order": "C", "quantization": None, "unit": "token_position"}


POLICY = {"name": "first-128-rows/1", "sha256": sha(b"first-128-rows/1")}
TID = sha(b"original RAW rows")


def origin_envelope(length: int, seq: int = 1, tid: str = TID) -> dict[str, Any]:
    """The original trajectory (a draft nvs.hidden-trajectory artifact; only raw_ref.trajectory_id, length, position are read)."""
    payload = {"source": "T-hid", "position": "p1", "layer": 12, "length": length, "dimension": D,
               "raw_ref": {"format": "TRJ_V2", "trajectory_id": tid, "copied": False}}
    env = _env(name="sensos-inference", kind="observation", payload=payload, seq=seq, session=SES, obs=OBS, space_id="H0")
    env["contract"]["version"] = "1.1.0"
    env["payload_schema"] = {"id": "nvs.hidden-trajectory", "version": "0.1.0-draft"}
    return seal(env, {})


def window_payload(**over: Any) -> dict[str, Any]:
    data = rows()
    pts = points_ref(data)
    payload = {
        "window": {"rule": "prefix_rows", "start": 0, "length": L, "content_sha256": sha(data)},
        "origin": {"trajectory_id": TID, "position": "p1", "length": 300},
        "source": "T-hid", "layer": 12, "dimension": D, "model_build_id": "m1",
        "policy": copy.deepcopy(POLICY), "points": pts, "token_index": index_ref(list(range(L))),
    }
    for k, v in over.items():
        payload[k] = v
    return payload


def window_envelope(payload: dict[str, Any], parent: str | None, lookup: dict[str, Any], *, seq: int = 2, kind: str = "observation",
                    producer: str = "nvs-runtime", space_id: str | None = "S1", parents: list[dict[str, Any]] | None = None,
                    schema_version: str = "0.9.0") -> dict[str, Any]:
    plist = parents if parents is not None else ([{"role": "source_trajectory", "ordered": False, "artifact_ids": [parent]}] if parent else [])
    env = _env(name=producer, kind=kind, payload=payload, seq=seq, session=SES, obs=OBS, parents=plist, space_id=space_id)
    env["contract"]["version"] = "1.1.0"
    env["payload_schema"] = {"id": "msr.trajectory-window", "version": schema_version}
    return seal(env, lookup)


def series_for(length: int) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Thresholds all null, no codebook: the undefined positions of msr/README.md, written by hand."""
    step = 3 << 30
    values = {n: [U] * length for n in SERIES}
    last: dict[str, int | None] = {n: None for n in SERIES}
    if length >= 2:
        for n in ("displacement_mean", "displacement_median"):
            values[n] = [U] + [step] * (length - 1)
            last[n] = step
        values["diversity_participation_ratio"] = [U] + [1 << 30] * (length - 1)
        last["diversity_participation_ratio"] = 1 << 30
    payload, blobs = _series_payload(length, None, values, last)
    return payload, blobs


def single_payload(length: int, scope: dict[str, Any] | None, window_env: dict[str, Any] | None) -> dict[str, Any]:
    payload, blobs = series_for(length)
    for u, data in blobs.items():
        BLOBS[u] = data
    ref = payload["input_ref"]
    ref["length"], ref["dimension"] = length, D
    if window_env is not None:
        w = window_env["payload"]
        ref["model_build_id"], ref["policy"] = w["model_build_id"], copy.deepcopy(w["policy"])
        payload["layer"], payload["source"], payload["space_id"] = w["layer"], w["source"], window_env["space_id"]
    out = {}
    for k, v in payload.items():  # input_scope right after input_ref, as in the schema
        out[k] = v
        if k == "input_ref" and scope is not None:
            out["input_scope"] = scope
    return out


def scope_of(w: dict[str, Any]) -> dict[str, Any]:
    p = w["payload"]
    return {"kind": "window", "rule": "prefix_rows", "start": 0, "length": L,
            "source_trajectory_id": p["origin"]["trajectory_id"], "content_sha256": p["window"]["content_sha256"]}


def measurement(payload: dict[str, Any], parents: list[dict[str, Any]], lookup: dict[str, Any], *, version: str = "0.9.0", seq: int = 5,
                space_id: str | None = "S1") -> dict[str, Any]:
    env = _env(name="meaning-space-runtime", kind="interpretation", payload=payload, seq=seq, session=SES, obs=OBS, parents=parents, space_id=space_id)
    env["payload_schema"] = {"id": "msr.geometry-measurement", "version": version}
    return seal(env, lookup)


def main() -> None:
    cases: list[dict[str, Any]] = []
    ORIG = origin_envelope(300)
    ORIG3 = origin_envelope(3, seq=3, tid=sha(b"short original"))
    lk_orig = {ORIG["artifact_id"]: _stored(ORIG)}
    stored_orig = {ORIG["artifact_id"]: {"envelope": ORIG}}

    def case(cid: str, target: str, env: dict[str, Any], stored: dict[str, Any], lookup: dict[str, Any], ic00: list[str], payload: list[str], note: str = "") -> None:
        got_ic00 = sorted({v.code for v in check_envelope_versioned(env, lookup)})
        got_payload = sorted({v.code for v in check_payload(env, stored, BLOBS)})
        assert got_ic00 == ic00 and got_payload == payload, (cid, "hand-written", ic00, payload, "implementation", got_ic00, got_payload)
        cases.append({"id": cid, "note": note, "target": target, "envelope": env, "stored": stored, "lookup": lookup,
                      "expect": {"result": "reject" if ic00 or payload else "accept", "ic00": ic00, "payload": payload}})

    def win(cid: str, payload: dict[str, Any], ic00: list[str], payload_codes: list[str], note: str = "", **kw: Any) -> dict[str, Any]:
        parent = kw.pop("parent", ORIG["artifact_id"])
        env = window_envelope(payload, parent, lk_orig, **kw)
        case(cid, "window", env, stored_orig, lk_orig, ic00, payload_codes, note)
        return env

    # ---- window artifact: accept
    GOOD = win("accept-window-first-128", window_payload(), [], [], "the normal window: 128 rows, parent = the original, nvs-runtime, observation")
    win("accept-window-token-index-not-from-zero", window_payload(token_index=index_ref(list(range(7, 7 + L)))), [], [], "token_index is the original's first 128 entries; it need not start at 0, only strictly increase")
    # ---- window artifact: length / start / shape
    p = window_payload(); p["window"]["length"] = 127
    win("reject-window-length-127", p, [], ["schema"], "declared length is not 128 (fixed window)")
    p = window_payload(); p["window"]["length"] = 129
    win("reject-window-length-129", p, [], ["schema"])
    p = window_payload(); p["window"]["start"] = 1
    win("reject-window-start-1", p, [], ["schema"], "start is fixed at 0")
    d127 = rows(127)
    p = window_payload(points=points_ref(d127, 127), token_index=index_ref(list(range(127))))
    p["window"]["content_sha256"] = sha(d127)
    win("reject-window-points-127-rows", p, [], ["schema"], "points.shape[0] is 127 (the schema fixes 128 rows)")
    p = window_payload()
    p["points"]["shape"] = [L, D + 1]
    win("reject-window-points-shape-differs-from-dimension", p, [], ["window_shape"], "shape [128, D+1] but dimension D")
    short = rows(127)
    pr = points_ref(short, L, D)  # shape says 128 x D, the bytes hold 127 rows
    p = window_payload(points=pr)
    p["window"]["content_sha256"] = pr["sha256"]
    win("reject-window-bytes-127-rows-shape-128", p, [], ["window_shape"], "the Blob has 127 rows of bytes but declares 128")
    ti = list(range(L)); ti[10] = ti[9]
    win("reject-window-token-index-not-increasing", window_payload(token_index=index_ref(ti)), [], ["window_shape"])
    # ---- window artifact: sha256
    p = window_payload(); p["window"]["content_sha256"] = "1" * 64
    win("reject-window-content-sha256-differs-from-points", p, [], ["window_sha256"], "window.content_sha256 is not points.sha256")
    data = rows(offset=9.0)
    p = window_payload(); p["points"]["sha256"] = sha(data); p["points"]["uri"] = "blob:sha256:" + sha(data)
    p["window"]["content_sha256"] = sha(data)  # consistent declaration, but the bytes held under it are the original window's
    BLOBS["blob:sha256:" + sha(data)] = rows()
    win("reject-window-bytes-differ-from-sha256", p, [], ["window_sha256"], "the bytes stored under the declared sha256 are other bytes")
    p = window_payload(); p["points"]["uri"] = "blob:sha256:" + "2" * 64
    win("reject-window-uri-differs-from-sha256", p, [], ["window_sha256"])
    nan = bytearray(rows()); nan[0:4] = struct.pack("<f", math.nan)
    pr = points_ref(bytes(nan))
    p = window_payload(points=pr); p["window"]["content_sha256"] = pr["sha256"]
    win("reject-window-has-nan", p, [], ["window_nonfinite"])
    p = window_payload(); p["policy"]["sha256"] = "3" * 64
    win("reject-window-policy-sha256-differs-from-name", p, [], ["window_policy"])
    # ---- window artifact: reference to the original
    win("reject-window-parents-empty", window_payload(), [], ["window_parents"], "the reference to the original trajectory is missing", parent=None)
    win("reject-window-parent-role-is-trajectory", window_payload(), [], ["window_parents"], "the parent must be role source_trajectory",
        parents=[{"role": "trajectory", "ordered": False, "artifact_ids": [ORIG["artifact_id"]]}])
    win("reject-window-parent-ordered-true", window_payload(), [], ["window_parents"], "", parents=[{"role": "source_trajectory", "ordered": True, "artifact_ids": [ORIG["artifact_id"]]}])
    two = origin_envelope(300, seq=1, tid=sha(b"another original"))
    lk2 = {**lk_orig, two["artifact_id"]: _stored(two)}
    env = window_envelope(window_payload(), None, lk2, parents=[{"role": "source_trajectory", "ordered": False, "artifact_ids": sorted([ORIG["artifact_id"], two["artifact_id"]])}])
    case("reject-window-two-source-trajectories", "window", env, {**stored_orig, two["artifact_id"]: {"envelope": two}}, lk2, [], ["window_parents"])
    ghost = "art:" + "9" * 64
    env = window_envelope(window_payload(), ghost, {ghost: {"content_id": "cnt:" + "9" * 64, "seq": 1, "observation_id": OBS}})  # sealed as if it existed
    case("reject-window-source-not-stored", "window", env, {}, {}, ["S8", "parent_unknown"], ["parent_unknown"], "the referenced original is not in HEKB (IC-00 1.1.0: parent_unknown, and S8 because no parent gives the observation_id; D-116 (2), (3))")
    p = window_payload(); p["origin"]["trajectory_id"] = "4" * 64
    win("reject-window-origin-trajectory-id-differs-from-stored", p, [], ["window_origin"], "origin.trajectory_id is not the stored original's")
    p = window_payload(); p["origin"]["length"] = 299
    win("reject-window-origin-length-differs-from-stored", p, [], ["window_origin"])
    p = window_payload(); p["origin"]["position"] = "p2"
    win("reject-window-origin-position-differs-from-stored", p, [], ["window_origin"], "the acquisition position")
    p = window_payload(); p["origin"]["length"] = 100
    win("reject-window-origin-shorter-than-window", p, [], ["schema"], "the original cannot be shorter than 128 rows")
    p = window_payload(); del p["origin"]
    win("reject-window-origin-missing", p, [], ["schema"], "payload.origin missing")
    p = window_payload(); p["extra"] = 1
    win("reject-window-extra-field", p, [], ["schema"])
    ev = origin_envelope(300); ev["payload"] = {"length": 300}
    ev = seal(ev, {})
    envx = window_envelope(window_payload(), ev["artifact_id"], {ev["artifact_id"]: _stored(ev)})
    case("reject-window-stored-parent-unreadable", "window", envx, {ev["artifact_id"]: {"envelope": ev}}, {ev["artifact_id"]: _stored(ev)}, [], ["window_origin_unreadable"], "the stored parent lacks raw_ref/position")
    # ---- window artifact: kind / producer / space
    win("reject-window-kind-interpretation", window_payload(), [], ["window_kind"], "IC-00 allows nvs-runtime x interpretation; the window contract does not", kind="interpretation")
    win("reject-window-producer-sensos-inference", window_payload(), [], ["window_producer"], "IC-00 1.1.0 allows sensos-inference x observation; the window contract names nvs-runtime", producer="sensos-inference")
    win("reject-window-producer-not-registered", window_payload(), ["S4"], ["window_producer"], "IC-00 S4 and the window contract both reject", producer="unknown-part")
    win("reject-window-space-id-null", window_payload(), [], ["window_space"], "", space_id=None)
    # ---- measurement: scope
    WIN = GOOD
    lk_w = {WIN["artifact_id"]: _stored(WIN)}
    st_w = {WIN["artifact_id"]: {"envelope": WIN}}
    par_w = [{"role": "trajectory", "ordered": False, "artifact_ids": [WIN["artifact_id"]]}]

    def meas(cid: str, payload: dict[str, Any], ic00: list[str], pcodes: list[str], note: str = "", parents: list[dict[str, Any]] | None = None,
             lookup: dict[str, Any] | None = None, stored: dict[str, Any] | None = None, **kw: Any) -> None:
        lk = lk_w if lookup is None else lookup
        env = measurement(payload, par_w if parents is None else parents, {**lk_w, **lk_orig, **lk}, **kw)  # sealed with every parent known; the Gate gets ``lk``
        case(cid, "measurement", env, st_w if stored is None else stored, lk, ic00, pcodes, note)

    meas("accept-single-window-scope", single_payload(L, scope_of(WIN), WIN), [], [], "single measurement of a window: input_scope window, parent = the window artifact")
    full = single_payload(3, {"kind": "full"}, None)
    lk3 = {ORIG3["artifact_id"]: _stored(ORIG3)}
    st3 = {ORIG3["artifact_id"]: {"envelope": ORIG3}}
    par3 = [{"role": "trajectory", "ordered": False, "artifact_ids": [ORIG3["artifact_id"]]}]
    full["space_id"] = "H0"
    env = measurement(full, par3, lk3, space_id="H0")
    case("accept-single-full-scope", "measurement", env, st3, lk3, [], [], "no window: input_scope full, parent = a whole (non-window) trajectory; the length is the trajectory's")
    full_bad = copy.deepcopy(full)
    full_bad["input_ref"]["length"] = 2
    full_bad["series"] = single_payload(2, {"kind": "full"}, None)["series"]
    full_bad["metrics"] = single_payload(2, {"kind": "full"}, None)["metrics"]
    env = measurement(full_bad, par3, lk3, space_id="H0")
    case("reject-single-full-scope-length-differs-from-parent", "measurement", env, st3, lk3, [], ["full_length_mismatch"], "a prefix measured without saying it is a window")
    meas("reject-single-full-scope-but-parent-is-window", single_payload(L, {"kind": "full"}, WIN), [], ["window_undeclared"], "a window used as a full trajectory")
    meas("reject-single-scope-missing", single_payload(L, None, WIN), [], ["schema"], "0.9.0 requires input_scope")
    p = single_payload(L, scope_of(WIN), WIN); p["input_ref"]["length"] = 127
    meas("reject-single-window-input-length-127", p, [], ["schema"], "input_ref.length must be 128 under a window scope")
    p = single_payload(L, scope_of(WIN), WIN); p["input_scope"]["length"] = 127
    meas("reject-single-window-scope-length-127", p, [], ["schema"])
    p = single_payload(L, scope_of(WIN), WIN); p["input_scope"]["start"] = 1
    meas("reject-single-window-scope-start-1", p, [], ["schema"])
    p = single_payload(L, scope_of(WIN), WIN); p["input_scope"]["source_trajectory_id"] = "5" * 64
    meas("reject-single-window-scope-source-differs-from-window", p, [], ["window_mismatch"], "the original trajectory the scope names is not the window's")
    p = single_payload(L, scope_of(WIN), WIN); p["input_scope"]["content_sha256"] = "6" * 64
    meas("reject-single-window-scope-content-sha256-differs", p, [], ["window_mismatch"], "the window's content the scope names is not the parent's")
    p = single_payload(L, scope_of(WIN), WIN); p["input_ref"]["dimension"] = D + 1
    meas("reject-single-window-input-dimension-differs", p, [], ["window_mismatch"])
    meas("reject-single-window-parent-missing", single_payload(L, scope_of(WIN), WIN), [], ["window_parent"], "scope is window but there is no trajectory parent", parents=[])
    meas("reject-single-window-parent-is-full-trajectory", single_payload(L, scope_of(WIN), WIN), [], ["window_not_window"], "scope is window but the parent is the whole trajectory",
         parents=[{"role": "trajectory", "ordered": False, "artifact_ids": [ORIG["artifact_id"]]}], lookup=lk_orig, stored=stored_orig)
    meas("reject-single-window-parent-not-stored", single_payload(L, scope_of(WIN), WIN), ["S8", "parent_unknown"], ["parent_unknown"], "the window is not in HEKB (S8 as above)", lookup={}, stored={})
    # ---- old rule (IC-02 0.8.0): still read, never asked for a window
    old = single_payload(L, None, WIN)
    meas("accept-single-0.7.1-old-rule-no-scope", old, [], [], "payload_schema 0.7.1 (IC-02 0.8.0): no input_scope, read by the old rule even though the parent is a window", version="0.7.1")
    old2 = single_payload(L, scope_of(WIN), WIN)
    meas("reject-single-0.7.1-with-input-scope", old2, [], ["schema"], "the old rule has no input_scope (never read as 0.9.0)", version="0.7.1")
    # ---- pair of windows: unchanged by 0.9.0
    WIN2 = window_envelope(window_payload(token_index=index_ref(list(range(L)))), ORIG["artifact_id"], lk_orig, seq=3)
    pair = {"mode": "pair", "space_id": "S1",
            "inputs": {"left": {"sha256": SHA, "model_build_id": "m1", "policy": copy.deepcopy(POLICY), "length": L, "dimension": D},
                       "right": {"sha256": SHA, "model_build_id": "m1", "policy": copy.deepcopy(POLICY), "length": L, "dimension": D}},
            "calibration": None, "alignment": {"mode": "equal_only", "points_used": L},
            "distance": {"definition": "mean_step_l2", "value": 5}, "verdict": {"state": "UNCALIBRATED"}}
    lk_p = {**lk_w, WIN2["artifact_id"]: _stored(WIN2)}
    st_p = {**st_w, WIN2["artifact_id"]: {"envelope": WIN2}}
    par_p = [{"role": "left", "ordered": False, "artifact_ids": [WIN["artifact_id"]]}, {"role": "right", "ordered": False, "artifact_ids": [WIN2["artifact_id"]]}]
    meas("accept-pair-of-windows-unchanged", pair, [], [], "pair is not changed by 0.9.0: two windows are two artifacts compared (equal_only)", parents=par_p, lookup=lk_p, stored=st_p)

    doc = {
        "format": "IC-02 0.9.0 window vectors: one case = envelope + stored + lookup; blobs are shared (uri -> hex)",
        "rule": "expect.ic00 = check_envelope_versioned(envelope, lookup); expect.payload = check_payload(envelope, stored, blobs). accept = both empty. Codes are in tools/contracts/ic02_window.py and msr/README.md (window).",
        "blobs": {u: d.hex() for u, d in sorted(BLOBS.items())},
        "cases": cases,
    }
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    acc = sum(c["expect"]["result"] == "accept" for c in cases)
    print(f"{len(cases)} cases, {acc} accept, {len(cases) - acc} reject -> {OUT}")


if __name__ == "__main__":
    main()
