"""Generate the IC-02 0.10.0 window vectors (D-132: a window with a position and a length).

Run:  python tools/contracts/make_vectors_window_rows.py  (from the repository root)

Two files, written together:

* ``msr/vectors/window-rows.json``              -- DETERMINED cases: every expectation follows from the wording of a decision
  (D-129, D-120, D-132 items 1-6, D-133 items 1-5). Frozen with the 0.10.0 lock.
* ``msr/vectors/window-rows-undetermined.json`` -- cases the decisions' wording does NOT settle (tag ``未規定``): after D-133, the pair of windows at different
  positions (D-133 (6)) and the token-number/row-number correspondence. They record what this implementation does. NOT in the lock, NOT part of the freeze.

Every expected code is written by hand below, with the decision text it comes from in ``derives_from``; the generator then runs the
implementation and refuses to write when one case disagrees. It reuses the builders of ``make_vectors_window.py`` (0.9.0).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import contracts.make_vectors_window as mv  # noqa: E402
from contracts.gate import check_payload  # noqa: E402
from contracts.ic00_versions import check_envelope_versioned  # noqa: E402
from contracts.make_vectors import SHA, _stored  # noqa: E402

CONTRACTS = Path(__file__).resolve().parents[2] / "docs/architecture/contracts/msr/vectors"
OUT = CONTRACTS / "window-rows.json"
OUT_UNDETERMINED = CONTRACTS / "window-rows-undetermined.json"
D = mv.D
V = "0.10.0"

D132_1 = "D-132 (1): 新しい rule `rows`。start と length は整数 (start >= 0、length >= 1)。`prefix_rows` は start=0 の特別な場合として残す"
D132_2 = "D-132 (2): window の payload と input_scope が rule・start・length を宣言する"
D132_3 = "D-132 (3): Gate が start + length <= origin.length と token_index の範囲を検査する。長さの異なる窓どうしの比較は equal_only ではできない (common_prefix は採らない。D-120)"
D132_3A = "D-132 (3) の前半: start + length <= origin.length"
D132_3B = "D-132 (3) の後半: 長さの異なる窓どうしの比較は equal_only ではできない (common_prefix は採らない。D-120)"
D132_4 = "D-132 (4): 窓の空間 (space_id) は row_rule に位置 (start、length) を含めて分ける。位置ごとの校正は別の空間"
D132_5 = "D-132 (5): 位置の候補 (先頭・中ほど・末尾など) を契約で狭めない"
D132_6 = "D-132 (6): 0.9.0 のスキーマは archive/ に移し、Gate は 0.9.0 と 0.10.0 の両方を受け付ける"
D129_PARENT = "D-129 (msr/README.md 窓の成果物): 親は役割 source_trajectory の 1 件 (ordered false)。元の成果物は HEKB にある"
D129_ORIGIN = "D-129 (msr/README.md 窓の成果物): origin は保存されている元の軌跡の raw_ref.trajectory_id・length・position と一致する"
D129_SHAPE = "D-129 (msr/README.md 窓の成果物): points は窓の行数 x dimension の binary32、token_index は行数の int64 (厳密に増える)"
D129_POLICY = "D-129 (msr/README.md): policy.sha256 は policy.name の UTF-8 の sha256"
D129_SCOPE = "D-129 (msr/README.md 計測): input_scope が窓を宣言し、親の窓と一致する。input_ref.length は scope.length"
D133_1 = "D-133 (1): token_index の範囲は [0, origin.length) の外を拒否する"
D133_2 = "D-133 (2): prefix_rows の長さは 128 に固定せず、任意の length (1 以上) を許す"
D133_3 = "D-133 (3): policy.name の形式は自由な文字列のまま"
D133_4 = "D-133 (4): 同じ space_id を位置の違う窓が使うと (start, length) を比べて拒否する (window_space_position)"
D133_5 = "D-133 (5): 0.10.0 の計測は 0.9.0 の窓 (start=0 の prefix_rows) を親にできる"
D133_6 = "D-133 (6): 位置の違う窓の比較 (equal_only は長さだけを見る) は未規定のまま。窓位置の実験では同じ位置どうしだけを比べる"
D132_8 = "D-132 (8): 見本の項目 (正常系・境界・start 負・length 0・型違い・prefix_rows との等価・0.9.0 の窓の読み込み・space_id の分離・親参照の整合)"

HEAD_SPACE, MID_SPACE, TAIL_SPACE = "SW-head", "SW-mid", "SW-tail"
TID1500 = mv.sha(b"original RAW rows, 1500")
TID100 = mv.sha(b"original RAW rows, 100")


def policy_name(rule: str, start: int, length: int) -> str:
    return f"first-{length}-rows/1" if rule == "prefix_rows" else f"rows-{start}+{length}/1"


def payload_of(rule: str, start: int, length: int, *, origin_length: int = 300, tid: str = mv.TID, token: list[int] | None = None,
               name: str | None = None, dimension: int = D, version: str = V) -> dict[str, Any]:
    data = mv.rows(length, dimension, offset=float(start))
    pts = mv.points_ref(data, length, dimension)
    nm = name if name is not None else policy_name(rule, start, length)
    return {
        "window": {"rule": rule, "start": start, "length": length, "content_sha256": mv.sha(data)},
        "origin": {"trajectory_id": tid, "position": "p1", "length": origin_length},
        "source": "T-hid", "layer": 12, "dimension": dimension, "model_build_id": "m1",
        "policy": {"name": nm, "sha256": mv.sha(nm.encode())}, "points": pts,
        "token_index": mv.index_ref(token if token is not None else list(range(start, start + length))),
    }


def scope_of(w: dict[str, Any]) -> dict[str, Any]:
    p = w["payload"]
    return {"kind": "window", "rule": p["window"]["rule"], "start": p["window"]["start"], "length": p["window"]["length"],
            "source_trajectory_id": p["origin"]["trajectory_id"], "content_sha256": p["window"]["content_sha256"]}


def main() -> None:
    confirmed: list[dict[str, Any]] = []
    undetermined: list[dict[str, Any]] = []
    ORIG = mv.origin_envelope(300)
    ORIG1500 = mv.origin_envelope(1500, seq=1, tid=TID1500)
    ORIG100 = mv.origin_envelope(100, seq=1, tid=TID100)
    origins = (ORIG, ORIG1500, ORIG100)
    lk = {o["artifact_id"]: _stored(o) for o in origins}
    st = {o["artifact_id"]: {"envelope": o} for o in origins}

    def case(into: list[dict[str, Any]], cid: str, target: str, env: dict[str, Any], stored: dict[str, Any], lookup: dict[str, Any],
             ic00: list[str], payload: list[str], derives: list[str], note: str = "", why_undetermined: str | None = None) -> None:
        got_ic00 = sorted({v.code for v in check_envelope_versioned(env, lookup)})
        got_payload = sorted({v.code for v in check_payload(env, stored, mv.BLOBS)})
        assert got_ic00 == ic00 and got_payload == payload, (cid, "hand-written", ic00, payload, "implementation", got_ic00, got_payload)
        c: dict[str, Any] = {"id": cid, "note": note, "target": target, "envelope": env, "stored": stored, "lookup": lookup,
                             "expect": {"result": "reject" if ic00 or payload else "accept", "ic00": ic00, "payload": payload},
                             "derives_from": derives}
        if why_undetermined is not None:
            c["tag"] = "未規定"
            c["undetermined_because"] = why_undetermined
        into.append(c)

    def win(into: list[dict[str, Any]], cid: str, payload: dict[str, Any], codes: list[str], derives: list[str], note: str = "", *,
            space: str | None = HEAD_SPACE, origin: dict[str, Any] | None = None, extra_stored: dict[str, Any] | None = None,
            version: str = V, why: str | None = None, **kw: Any) -> dict[str, Any]:
        o = origin or ORIG
        env = mv.window_envelope(payload, kw.pop("parent", o["artifact_id"]), lk, space_id=space, schema_version=version, **kw)
        case(into, cid, "window", env, {**st, **(extra_stored or {})}, lk, [], codes, derives, note, why)
        return env

    # ============================================================ DETERMINED: window artifact, accept
    HEAD = win(confirmed, "accept-rows-head", payload_of("rows", 0, 128), [], [D132_1, D132_5], "position: head (start 0) as rows", space=HEAD_SPACE)
    MID = win(confirmed, "accept-rows-middle", payload_of("rows", 86, 128), [], [D132_1, D132_5], "position: middle (start 86, length 128, origin 300)", space=MID_SPACE)
    TAIL = win(confirmed, "accept-rows-tail", payload_of("rows", 1372, 128, origin_length=1500, tid=TID1500), [], [D132_1, D132_5],
               "position: tail of a 1500-row original; start + length == origin.length (the boundary itself)", space=TAIL_SPACE, origin=ORIG1500)
    win(confirmed, "accept-rows-boundary-end-equals-origin-length", payload_of("rows", 172, 128), [], [D132_3A],
        "start + length == origin.length (300): the last allowed window", space=TAIL_SPACE)
    win(confirmed, "accept-rows-length-64", payload_of("rows", 40, 64), [], [D132_1, D132_5], "the length need not be 128 (length >= 1)", space="SW-40+64")
    win(confirmed, "accept-rows-length-1", payload_of("rows", 5, 1), [], [D132_1], "length 1 is the minimum", space="SW-5+1")
    win(confirmed, "accept-prefix-rows-128", payload_of("prefix_rows", 0, 128), [], [D132_1], "prefix_rows is kept as the special case start = 0", space=HEAD_SPACE)
    # equivalence: the same rows declared as prefix_rows and as rows(start 0); same policy name so only window.rule differs
    pe = payload_of("prefix_rows", 0, 128, name="first-128-rows/1")
    re_ = payload_of("rows", 0, 128, name="first-128-rows/1")
    assert pe["window"]["content_sha256"] == re_["window"]["content_sha256"] and pe["points"] == re_["points"]
    win(confirmed, "accept-equivalence-prefix-rows-start-0", pe, [], [D132_1], "equivalence, 1/2: prefix_rows, start 0, 128 rows", space=HEAD_SPACE)
    win(confirmed, "accept-equivalence-rows-start-0", re_, [], [D132_1], "equivalence, 2/2: rows, start 0, the very same 128 rows and Blob; the Gate's verdict is the same", space=HEAD_SPACE)

    # ============================================================ DETERMINED: window artifact, reject
    win(confirmed, "reject-rows-end-exceeds-origin-by-1", payload_of("rows", 173, 128, token=list(range(171, 171 + 128))), ["window_range"], [D132_3A], "start + length == origin.length + 1", space=TAIL_SPACE)
    for cid, mutate, note in (
        ("reject-rows-start-negative", lambda p: p["window"].__setitem__("start", -1), "start >= 0"),
        ("reject-rows-length-zero", lambda p: p["window"].__setitem__("length", 0), "length >= 1"),
        ("reject-rows-length-negative", lambda p: p["window"].__setitem__("length", -128), "length >= 1"),
        ("reject-rows-start-string", lambda p: p["window"].__setitem__("start", "0"), "start is an integer, not a string"),
        ("reject-rows-length-string", lambda p: p["window"].__setitem__("length", "128"), "length is an integer, not a string"),
        ("reject-rows-start-boolean", lambda p: p["window"].__setitem__("start", True), "start is an integer, not a boolean"),
        ("reject-rows-start-null", lambda p: p["window"].__setitem__("start", None), "start is an integer, not null"),
        ("reject-window-rule-unknown-suffix-rows", lambda p: p["window"].__setitem__("rule", "suffix_rows"), "the rules are prefix_rows and rows; a tail is a rows window"),
    ):
        p = payload_of("rows", 0, 128)
        mutate(p)
        win(confirmed, cid, p, ["schema"], [D132_1], note, space=HEAD_SPACE)
    p = payload_of("prefix_rows", 0, 128)
    p["window"]["start"] = 5
    win(confirmed, "reject-prefix-rows-start-nonzero", p, ["schema"], [D132_1], "prefix_rows is the case start = 0", space=HEAD_SPACE)
    p = payload_of("rows", 0, 128)
    del p["window"]["length"]
    win(confirmed, "reject-rows-length-missing", p, ["schema"], [D132_2], "the window declares rule, start and length", space=HEAD_SPACE)
    p = payload_of("rows", 86, 128)
    p["points"]["shape"] = [127, D]
    win(confirmed, "reject-rows-points-shape-differs-from-length", p, ["window_shape"], [D129_SHAPE, D132_2], "points.shape[0] 127 while window.length is 128", space=MID_SPACE)
    p = payload_of("rows", 86, 128, token=list(range(86, 86 + 127)))
    p["token_index"]["shape"] = [127]
    win(confirmed, "reject-rows-token-index-count-differs-from-length", p, ["window_shape"], [D129_SHAPE, D132_2], "token_index holds 127 entries while window.length is 128", space=MID_SPACE)
    p = payload_of("rows", 86, 128)
    p["policy"]["sha256"] = "3" * 64
    win(confirmed, "reject-rows-policy-sha256-differs-from-name", p, ["window_policy"], [D129_POLICY], "", space=MID_SPACE)
    p = payload_of("rows", 86, 128)
    p["window"]["content_sha256"] = "1" * 64
    win(confirmed, "reject-rows-content-sha256-differs-from-points", p, ["window_sha256"], [D129_SHAPE], "window.content_sha256 is not points.sha256", space=MID_SPACE)
    ti = list(range(86, 86 + 128))
    ti[10] = ti[9]
    win(confirmed, "reject-rows-token-index-not-increasing", payload_of("rows", 86, 128, token=ti), ["window_shape"], [D129_SHAPE], "", space=MID_SPACE)
    win(confirmed, "reject-rows-parents-empty", payload_of("rows", 86, 128), ["window_parents"], [D129_PARENT], "no reference to the original", space=MID_SPACE, parent=None)
    p = payload_of("rows", 86, 128)
    p["origin"]["trajectory_id"] = "4" * 64
    win(confirmed, "reject-rows-origin-trajectory-id-differs-from-stored", p, ["window_origin"], [D129_ORIGIN], "", space=MID_SPACE)
    p = payload_of("rows", 86, 128)
    p["origin"]["length"] = 299
    win(confirmed, "reject-rows-origin-length-differs-from-stored", p, ["window_origin"], [D129_ORIGIN], "", space=MID_SPACE)
    ghost = "art:" + "9" * 64
    env = mv.window_envelope(payload_of("rows", 86, 128), ghost, {ghost: {"content_id": "cnt:" + "9" * 64, "seq": 1, "observation_id": mv.OBS}}, space_id=MID_SPACE, schema_version=V)
    case(confirmed, "reject-rows-source-not-stored", "window", env, {}, {}, ["S8", "parent_unknown"], ["parent_unknown"], [D129_PARENT], "the original is not in HEKB")
    win(confirmed, "reject-rows-space-id-null", payload_of("rows", 86, 128), ["window_space"], [D132_4, "D-129 (msr/README.md): 窓の封筒の space_id は null でない"], "", space=None)

    # ============================================================ DETERMINED: space separation
    env = mv.window_envelope(payload_of("rows", 172, 128), ORIG["artifact_id"], lk, space_id=TAIL_SPACE, schema_version=V)
    case(confirmed, "accept-windows-of-one-original-in-separate-spaces", "window", env, {**st, HEAD["artifact_id"]: {"envelope": HEAD}, MID["artifact_id"]: {"envelope": MID}},
         lk, [], [], [D132_4, D132_5], "head and middle windows of the same original are stored in their own spaces; the tail window, in a third, is accepted beside them")
    env = mv.window_envelope(payload_of("rows", 0, 128, origin_length=1500, tid=TID1500), ORIG1500["artifact_id"], lk, space_id=HEAD_SPACE, schema_version=V)
    case(confirmed, "accept-same-position-in-the-same-space-for-another-original", "window", env, {**st, HEAD["artifact_id"]: {"envelope": HEAD}}, lk, [], [],
         [D132_4], "same start and length (0, 128) as the stored head window, another original: one space per position")

    # ============================================================ DETERMINED: 0.9.0 windows are read
    g090 = mv.window_payload()
    env090 = mv.window_envelope(g090, ORIG["artifact_id"], lk, space_id="S1", schema_version="0.9.0")
    case(confirmed, "accept-0.9.0-window-first-128", "window", env090, st, lk, [], [], [D132_6, "D-132 (1): 0.9.0 の窓の成果物は読める"], "payload_schema 0.9.0, read by its own (archived) rule")
    p = mv.window_payload()
    p["window"]["rule"] = "rows"
    env = mv.window_envelope(p, ORIG["artifact_id"], lk, space_id="S1", schema_version="0.9.0")
    case(confirmed, "reject-0.9.0-window-declaring-rows", "window", env, st, lk, [], ["schema"], [D132_6], "a 0.9.0 window is never read as 0.10.0: rule rows is not a 0.9.0 rule")
    p = mv.window_payload()
    p["window"]["length"] = 64
    env = mv.window_envelope(p, ORIG["artifact_id"], lk, space_id="S1", schema_version="0.9.0")
    case(confirmed, "reject-0.9.0-window-length-64", "window", env, st, lk, [], ["schema"], [D132_6], "0.9.0 stays fixed at 128 rows")

    # ============================================================ DETERMINED: measurement
    def meas(into: list[dict[str, Any]], cid: str, payload: dict[str, Any], codes: list[str], derives: list[str], note: str, w: dict[str, Any],
             *, ic00: list[str] | None = None, parents: list[dict[str, Any]] | None = None, stored: dict[str, Any] | None = None,
             lookup: dict[str, Any] | None = None, version: str = V, why: str | None = None) -> None:
        wl = {w["artifact_id"]: _stored(w)}
        par = parents if parents is not None else [{"role": "trajectory", "ordered": False, "artifact_ids": [w["artifact_id"]]}]
        env = mv.measurement(payload, par, {**lk, **wl, **(lookup or {})}, version=version, space_id=w["space_id"])
        case(into, cid, "measurement", env, stored if stored is not None else {**st, w["artifact_id"]: {"envelope": w}}, lookup if lookup is not None else wl,
             ic00 or [], codes, derives, note, why)

    meas(confirmed, "accept-single-scope-rows-head", mv.single_payload(128, scope_of(HEAD), HEAD), [], [D132_2, D129_SCOPE], "input_scope declares rule rows, start 0, length 128", HEAD)
    meas(confirmed, "accept-single-scope-rows-middle", mv.single_payload(128, scope_of(MID), MID), [], [D132_2, D132_5], "input_scope declares rows, start 86", MID)
    meas(confirmed, "accept-single-scope-rows-tail", mv.single_payload(128, scope_of(TAIL), TAIL), [], [D132_2, D132_5], "input_scope declares rows, start 1372 (tail of 1500)", TAIL)
    W64 = win(confirmed, "accept-rows-length-64-for-a-measurement", payload_of("rows", 40, 64), [], [D132_1], "a 64-row window (the measurement below measures it)", space="SW-40+64")
    meas(confirmed, "accept-single-scope-rows-length-64", mv.single_payload(64, scope_of(W64), W64), [], [D132_2, D129_SCOPE], "input_ref.length == scope.length == 64", W64)
    PW = win(confirmed, "accept-prefix-rows-for-a-measurement", payload_of("prefix_rows", 0, 128), [], [D132_1], "", space=HEAD_SPACE)
    meas(confirmed, "accept-single-scope-prefix-rows", mv.single_payload(128, scope_of(PW), PW), [], [D132_2], "input_scope declares prefix_rows, start 0", PW)
    p = mv.single_payload(128, scope_of(MID), MID)
    p["input_scope"]["start"] = 87
    meas(confirmed, "reject-single-scope-start-differs-from-window", p, ["window_mismatch"], [D132_2, D129_SCOPE], "scope.start 87, the window's is 86", MID)
    p = mv.single_payload(128, scope_of(HEAD), HEAD)
    p["input_scope"]["rule"] = "prefix_rows"
    meas(confirmed, "reject-single-scope-rule-differs-from-window", p, ["window_mismatch"], [D132_2, D129_SCOPE], "the window declares rows (start 0); the scope says prefix_rows", HEAD)
    p = mv.single_payload(128, scope_of(MID), MID)
    p["input_scope"]["length"] = 127
    meas(confirmed, "reject-single-scope-length-differs-from-window-and-input", p, ["window_length", "window_mismatch"], [D129_SCOPE], "scope.length 127 vs the window's 128 and input_ref.length 128", MID)
    p = mv.single_payload(127, scope_of(MID), MID)
    meas(confirmed, "reject-single-input-length-differs-from-scope", p, ["window_length"], [D129_SCOPE], "input_ref.length 127, scope.length 128 (0.9.0 had a schema constant; now the Gate says so)", MID)
    p = mv.single_payload(128, scope_of(MID), MID)
    p["input_scope"]["start"] = -1
    meas(confirmed, "reject-single-scope-start-negative", p, ["schema"], [D132_1, D132_2], "", MID)
    p = mv.single_payload(128, scope_of(MID), MID)
    p["input_scope"]["length"] = 0
    meas(confirmed, "reject-single-scope-length-zero", p, ["schema"], [D132_1, D132_2], "", MID)
    p = mv.single_payload(128, scope_of(MID), MID)
    p["input_scope"]["start"] = "86"
    meas(confirmed, "reject-single-scope-start-string", p, ["schema"], [D132_1, D132_2], "", MID)
    p = mv.single_payload(128, scope_of(HEAD), HEAD)
    p["input_scope"]["rule"] = "prefix_rows"
    p["input_scope"]["start"] = 3
    meas(confirmed, "reject-single-scope-prefix-rows-start-nonzero", p, ["schema"], [D132_1], "", HEAD)
    meas(confirmed, "reject-single-scope-missing", mv.single_payload(128, None, MID), ["schema"], [D132_2], "0.10.0 requires input_scope (as 0.9.0)", MID)
    meas(confirmed, "reject-single-scope-full-but-parent-is-window", mv.single_payload(128, {"kind": "full"}, MID), ["window_undeclared"], [D129_SCOPE], "a window used as a full trajectory", MID)

    # ============================================================ DETERMINED: pair (equal_only)
    def pair_payload(l1: int, l2: int, mode: str = "equal_only") -> dict[str, Any]:
        def ref(n: int, w: dict[str, Any]) -> dict[str, Any]:
            return {"sha256": SHA, "model_build_id": "m1", "policy": copy.deepcopy(w["payload"]["policy"]), "length": n, "dimension": D}
        return {"mode": "pair", "space_id": "S-pair", "inputs": {"left": ref(l1, HEAD), "right": ref(l2, HEAD)}, "calibration": None,
                "alignment": {"mode": mode, "points_used": min(l1, l2)}, "distance": {"definition": "mean_step_l2", "value": 5},
                "verdict": {"state": "UNCALIBRATED"}}

    def pair(into: list[dict[str, Any]], cid: str, left: dict[str, Any], right: dict[str, Any], codes: list[str], derives: list[str], note: str,
             payload: dict[str, Any], why: str | None = None) -> None:
        lw = {left["artifact_id"]: _stored(left), right["artifact_id"]: _stored(right)}
        par = [{"role": "left", "ordered": False, "artifact_ids": [left["artifact_id"]]}, {"role": "right", "ordered": False, "artifact_ids": [right["artifact_id"]]}]
        env = mv.measurement(payload, par, {**lk, **lw}, version=V, space_id="S-pair")
        case(into, cid, "measurement", env, {**st, **{a: {"envelope": e} for a, e in ((left["artifact_id"], left), (right["artifact_id"], right))}}, lw, [], codes, derives, note, why)

    pair(confirmed, "reject-pair-of-windows-of-different-lengths-equal-only", HEAD, W64, ["pair_window_length"], [D132_3B], "128 rows vs 64 rows cannot be compared with equal_only", pair_payload(128, 64))
    pair(confirmed, "reject-pair-of-windows-of-different-lengths-common-prefix", HEAD, W64, ["pair_window_length"], [D132_3B],
         "common_prefix (extension mode x-common_prefix) is not adopted (D-120): still rejected", pair_payload(128, 64, "x-common_prefix"))

    # ============================================================ D-133 (11-08 20:16): the five points the implementation chose are now determined
    ti_hi = list(range(290, 290 + 128))
    win(confirmed, "reject-token-index-beyond-origin-length", payload_of("rows", 172, 128, token=ti_hi), ["window_token_range"], [D133_1],
        "token_index 290..417 while origin.length is 300: outside [0, origin.length)", space=TAIL_SPACE)
    win(confirmed, "reject-token-index-negative", payload_of("rows", 0, 128, token=list(range(-3, 125))), ["window_token_range"], [D133_1], "a negative token number", space=HEAD_SPACE)
    win(confirmed, "reject-rows-longer-than-origin", payload_of("rows", 0, 128, origin_length=100, tid=TID100), ["window_range", "window_token_range"], [D133_1, D132_3A],
        "length 128 > origin.length 100: window_range (D-132 (3)); 128 strictly increasing token numbers cannot fit in [0, 100), so D-133 (1) rejects them too: the code set is both",
        space=HEAD_SPACE, origin=ORIG100)
    win(confirmed, "accept-policy-name-free-form", payload_of("rows", 86, 128, name="my-middle-window"), [], [D133_3],
        "policy.name is any non-empty string whose sha256 is policy.sha256 (first-N-rows/1 and rows-S+N/1 are conventions, not rules)", space=MID_SPACE)
    win(confirmed, "accept-prefix-rows-length-64", payload_of("prefix_rows", 0, 64), [], [D133_2], "prefix_rows is not fixed at 128: any length >= 1", space="SW-0+64")
    win(confirmed, "reject-space-shared-by-two-positions", payload_of("rows", 172, 128), ["window_space_position"], [D133_4],
        "a window whose space_id is already used by a stored window of another position (start, length) is rejected", space=HEAD_SPACE,
        extra_stored={HEAD["artifact_id"]: {"envelope": HEAD}})
    meas(confirmed, "accept-0.10.0-measurement-over-a-0.9.0-window", mv.single_payload(128, scope_of({"payload": g090, "artifact_id": ""}), env090), [],
         [D133_5], "a 0.10.0 measurement whose scope (prefix_rows, 0, 128) matches a 0.9.0 window parent (start 0)", env090)

    # ============================================================ UNDETERMINED (未規定): kept apart, not frozen (D-133 (6) and one more)
    win(undetermined, "undetermined-token-index-offset-from-row-numbers", payload_of("rows", 86, 128, token=list(range(7, 7 + 128))), [], [D133_1],
        "token_index 7..134 for the rows starting at row 86: accepted here (inside [0, origin.length); the token number need not equal the row number; 0.9.0 said the same for the head)",
        space=MID_SPACE, why="D-133 (1) は範囲 [0, origin.length) の外の拒否だけを決め、トークン番号と行番号の対応 (窓の行が元の何番目のトークンか) は決めていない")
    pair(undetermined, "undetermined-pair-of-equal-length-windows-at-different-positions", HEAD, MID, [], [D133_6],
         "128 rows head vs 128 rows middle: equal length, equal_only accepts here (equal_only looks at the length only)", pair_payload(128, 128),
         why="D-133 (6): 位置の違う窓の比較 (equal_only は長さだけを見る) は未規定。窓位置の実験では同じ位置どうしだけを比べる")

    # ============================================================ write
    def doc(cases: list[dict[str, Any]], fmt: str, extra: dict[str, Any]) -> dict[str, Any]:
        used = {u for c in cases for u in _uris(c)}
        return {"format": fmt,
                "rule": "expect.ic00 = check_envelope_versioned(envelope, lookup); expect.payload = check_payload(envelope, stored, blobs). accept = both empty. "
                        "derives_from = the decision wording each expectation follows from. Codes are in tools/contracts/ic02_window.py and msr/README.md (窓).",
                **extra, "blobs": {u: d.hex() for u, d in sorted(mv.BLOBS.items()) if u in used}, "cases": cases}

    OUT.write_text(json.dumps(doc(confirmed, "IC-02 0.10.0 window vectors (determined): one case = envelope + stored + lookup; blobs are shared (uri -> hex)",
                                  {"status": "確定 (D-132 と D-129 の文言から導いた期待。0.10.0 の lock に入る)"}), indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    OUT_UNDETERMINED.write_text(json.dumps(doc(undetermined, "IC-02 0.10.0 window vectors (未規定): what this implementation does where the decisions' wording does not decide",
                                               {"status": "未規定 (決定の文言だけでは決まらない。凍結の対象外・lock に入れない。決定が出たら確定側へ移すか実装を直す)"}),
                                indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    acc = sum(c["expect"]["result"] == "accept" for c in confirmed)
    uacc = sum(c["expect"]["result"] == "accept" for c in undetermined)
    print(f"determined: {len(confirmed)} cases, {acc} accept, {len(confirmed) - acc} reject -> {OUT}")
    print(f"undetermined: {len(undetermined)} cases, {uacc} accept, {len(undetermined) - uacc} reject -> {OUT_UNDETERMINED}")


def _uris(case_: dict[str, Any]) -> set[str]:
    out: set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            u = x.get("uri")
            if isinstance(u, str) and u.startswith("blob:sha256:"):
                out.add(u)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(case_["envelope"])
    walk(case_["stored"])
    return out


if __name__ == "__main__":
    main()
