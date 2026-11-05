"""Generate the language-neutral vectors (docs/architecture/contracts/common/vectors/).

Run:  python tools/contracts/make_vectors.py  (from the repository root)

jcs outputs of ``canonicalize.json`` are written by hand below (not produced by
jcs()), so they are an independent statement of RFC 8785. Envelope ids and
check results come from the reference implementation; they are frozen by the
files and re-derived by tests.
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
from contracts.check import check_envelope  # noqa: E402
from contracts.errors import ContractError  # noqa: E402
from contracts.jcs import jcs  # noqa: E402
from contracts.quantize import INT64_RANGE, quantize  # noqa: E402

VECTORS = Path(__file__).resolve().parents[2] / "docs/architecture/contracts/common/vectors"
SHA = "a" * 64


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bits(x: float) -> str:
    return struct.pack(">d", x).hex()


# ------------------------------------------------------------- canonicalize


def _acc(case_id: str, text: str, out: str, note: str = "") -> dict[str, Any]:
    return {
        "id": case_id,
        "note": note,
        "input_utf8": text,
        "expect": {"result": "accept", "jcs_utf8": out, "jcs_sha256": sha256_hex(out.encode())},
    }


def _rej(case_id: str, code: str, text: str | None = None, hex_: str | None = None, note: str = "") -> dict[str, Any]:
    case: dict[str, Any] = {"id": case_id, "note": note}
    if text is not None:
        case["input_utf8"] = text
    else:
        case["input_hex"] = hex_
    case["expect"] = {"result": "reject", "code": code}
    return case


def canonicalize_cases() -> list[dict[str, Any]]:
    return [
        _rej("dup-key-plain", "E_DUP_KEY", '{"a":1,"a":2}'),
        _rej("dup-key-escaped", "E_DUP_KEY", '{"value":100,"val\\u0075e":200}', note="keys compared after unescaping"),
        _rej("dup-key-nested", "E_DUP_KEY", '{"x":{"k":1,"k":2}}'),
        _rej("dup-key-in-array-object", "E_DUP_KEY", '[{"k":1,"k":1}]'),
        _rej("dup-key-surrogate-pair-escape", "E_DUP_KEY", '{"\U0001f600":1,"\\ud83d\\ude00":2}'),
        _acc("same-key-different-levels", '{"a":{"a":1}}', '{"a":{"a":1}}'),
        _acc(
            "no-unicode-normalization",
            '{"é":1,"é":2}',
            '{"é":2,"é":1}',
            "NFC/NFD forms are distinct keys; U+0065 sorts before U+00E9",
        ),
        _rej("float-1.0", "E_FLOAT_TOKEN", '{"a":1.0}', note="integral value, but a fraction token"),
        _rej("float-1e0", "E_FLOAT_TOKEN", '{"a":1e0}'),
        _rej("float-1E0", "E_FLOAT_TOKEN", '{"a":1E0}'),
        _rej("float-1.5", "E_FLOAT_TOKEN", '{"a":1.5}'),
        _rej("float-minus-zero-point-zero", "E_FLOAT_TOKEN", '{"a":-0.0}'),
        _rej("float-0e0", "E_FLOAT_TOKEN", '[0e0]'),
        _rej("nan", "E_CONSTANT", '{"a":NaN}'),
        _rej("infinity", "E_CONSTANT", '{"a":Infinity}'),
        _rej("minus-infinity", "E_CONSTANT", '{"a":-Infinity}'),
        _acc("minus-zero-integer", '{"a":-0}', '{"a":0}', "-0 is an integer token; its value is 0"),
        _acc("max-safe-integer", '{"a":9007199254740991}', '{"a":9007199254740991}'),
        _acc("min-safe-integer", '{"a":-9007199254740991}', '{"a":-9007199254740991}'),
        _rej("two-pow-53", "E_INT_RANGE", '{"a":9007199254740992}'),
        _rej("minus-two-pow-53", "E_INT_RANGE", '{"a":-9007199254740992}'),
        _rej("huge-integer", "E_INT_RANGE", '[123456789012345678901234567890]'),
        _rej("leading-zero", "E_SYNTAX", '{"a":01}'),
        _rej("plus-sign", "E_SYNTAX", '{"a":+1}'),
        _rej("trailing-comma", "E_SYNTAX", '[1,2,]'),
        _rej("empty-input", "E_SYNTAX", ""),
        _rej("single-quotes", "E_SYNTAX", "{'a':1}"),
        _rej("bom", "E_SYNTAX", None, "efbbbf7b7d", "a UTF-8 BOM is not JSON text"),
        _rej("invalid-utf8-byte", "E_UTF8", None, "7b2261223a22ff227d"),
        _rej("invalid-utf8-overlong", "E_UTF8", None, "7b2261223a22c0af227d"),
        _rej("invalid-utf8-encoded-surrogate", "E_UTF8", None, "7b2261223a22eda080227d", "ED A0 80 = U+D800"),
        _rej("lone-high-surrogate-escape", "E_SURROGATE", '{"a":"\\ud800"}'),
        _rej("lone-low-surrogate-escape", "E_SURROGATE", '{"a":"\\udc00"}'),
        _rej("lone-surrogate-in-key", "E_SURROGATE", '{"\\udc00":1}'),
        _rej("reversed-surrogate-pair", "E_SURROGATE", '{"a":"\\ude00\\ud83d"}'),
        _acc("valid-surrogate-pair-escape", '{"a":"\\ud83d\\ude00"}', '{"a":"\U0001f600"}'),
        _acc(
            "key-order-utf16",
            '{"\\uffff":1,"\\ud800\\udc00":2,"\\ue000":3,"a":4}',
            '{"a":4,"\U00010000":2,"":3,"￿":1}',
            "UTF-16 code units: a(0061) < U+10000 (D800 DC00) < U+E000 < U+FFFF; code-point order would differ",
        ),
        _acc("key-order-ascii", '{"b":2,"a":1,"10":3,"9":4,"1":5}', '{"1":5,"10":3,"9":4,"a":1,"b":2}'),
        _acc("key-prefix-order", '{"ab":1,"a":2}', '{"a":2,"ab":1}'),
        _acc("array-order-kept", "[3,1,2]", "[3,1,2]"),
        _acc("whitespace-ignored", ' { "a" : [ 1 , 2 ] , "b" : null }\n', '{"a":[1,2],"b":null}'),
        _acc("literals", "[true,false,null]", "[true,false,null]"),
        _acc("empty-containers", '{"a":{},"b":[]}', '{"a":{},"b":[]}'),
        _acc(
            "string-escapes",
            '{"a":"\\u0001\\u001f\\b\\f\\n\\r\\t\\"\\\\\\/"}',
            '{"a":"\\u0001\\u001f\\b\\f\\n\\r\\t\\"\\\\/"}',
            "short escapes for b f n r t, double quote and backslash; other controls as lower-case \\u00xx; solidus not escaped",
        ),
        _acc(
            "string-literal-specials",
            '{"a":"\\u007f\\u2028\\u2029\\u00e9"}',
            '{"a":"\u007f  é"}',
            "U+007F, U+2028, U+2029 and non-ASCII are written as themselves",
        ),
        _acc("negative-integers", "[-1,0,10,-10]", "[-1,0,10,-10]"),
    ]


# ----------------------------------------------------------------- quantize


def _q_accept(case_id: str, value: float, exponent: int, q: int, range_: str = "envelope", note: str = "") -> dict[str, Any]:
    return {
        "id": case_id,
        "op": "quantize",
        "note": note,
        "value_bits": bits(value),
        "value_repr": repr(value),
        "exponent": exponent,
        "range": range_,
        "expect": {"result": "accept", "q": q},
    }


def _q_reject(case_id: str, value: float, exponent: int, code: str, range_: str = "envelope", note: str = "") -> dict[str, Any]:
    case = _q_accept(case_id, value, exponent, 0, range_, note)
    case["expect"] = {"result": "reject", "code": code}
    return case


def quantize_cases() -> list[dict[str, Any]]:
    half = 2.0**-31  # half a quantum at exponent -30
    cases = [
        _q_accept("tie-0.5-to-0", half, -30, 0, note="0.5 quanta -> 0 (even)"),
        _q_accept("tie-1.5-to-2", 3 * half, -30, 2, note="1.5 quanta -> 2 (even)"),
        _q_accept("tie-2.5-to-2", 5 * half, -30, 2, note="2.5 quanta -> 2 (even)"),
        _q_accept("tie-3.5-to-4", 7 * half, -30, 4, note="3.5 quanta -> 4 (even)"),
        _q_accept("tie-neg-0.5-to-0", -half, -30, 0),
        _q_accept("tie-neg-1.5-to--2", -3 * half, -30, -2),
        _q_accept("tie-neg-2.5-to--2", -5 * half, -30, -2),
        _q_accept("just-above-half", math.nextafter(half, 1.0), -30, 1, note="next float above 0.5 quanta"),
        _q_accept("just-below-half", math.nextafter(half, 0.0), -30, 0),
        _q_accept("exact-3-quanta", 3 * 2.0**-30, -30, 3),
        _q_accept("zero", 0.0, -30, 0),
        _q_accept("negative-zero", -0.0, -30, 0),
        _q_accept("exp0-2.5", 2.5, 0, 2),
        _q_accept("exp0-3.5", 3.5, 0, 4),
        _q_accept("positive-exponent-tie", 6.0, 2, 2, note="quantum 4: 6/4 = 1.5 -> 2"),
        _q_accept("positive-exponent-tie-low", 2.0, 2, 0, note="quantum 4: 2/4 = 0.5 -> 0"),
        _q_accept("max-safe-quanta", (2**53 - 1) * 2.0**-30, -30, 2**53 - 1),
        _q_accept("min-safe-quanta", -((2**53 - 1) * 2.0**-30), -30, -(2**53 - 1)),
        _q_reject("two-pow-53-quanta", 2.0**53 * 2.0**-30, -30, "E_QUANT_RANGE"),
        _q_reject("minus-two-pow-53-quanta", -(2.0**53) * 2.0**-30, -30, "E_QUANT_RANGE"),
        _q_accept("int64-large-ok", 2.0**62, 0, 2**62, "int64"),
        _q_reject("int64-two-pow-63", 2.0**63, 0, "E_QUANT_RANGE", "int64"),
        _q_accept("int64-min", -(2.0**63), 0, -(2**63), "int64"),
        _q_reject("envelope-rejects-int64-value", 2.0**62, 0, "E_QUANT_RANGE", "envelope"),
        _q_reject("nan", float("nan"), -30, "E_QUANT_NONFINITE"),
        _q_reject("infinity", float("inf"), -30, "E_QUANT_NONFINITE"),
        _q_reject("minus-infinity", float("-inf"), -30, "E_QUANT_NONFINITE"),
        _q_reject("scaling-overflow", sys.float_info.max, -30, "E_QUANT_RANGE"),
        _q_accept("subnormal-to-zero", 5e-324, -30, 0),
    ]
    for case in cases:  # self-check the table against the reference implementation
        value = struct.unpack(">d", bytes.fromhex(case["value_bits"]))[0]
        rng = INT64_RANGE if case["range"] == "int64" else (-(2**53 - 1), 2**53 - 1)
        try:
            got: Any = {"result": "accept", "q": quantize(value, case["exponent"], int_range=rng)}
        except ContractError as exc:
            got = {"result": "reject", "code": exc.code}
        assert got == case["expect"], (case["id"], got)
    return cases


# --------------------------------------------------------------------- ids


def id_cases() -> list[dict[str, Any]]:
    spec = {
        "experiment_spec_hash": "sha256:" + "b" * 64,
        "item_id": "item-001",
        "condition": "baseline",
        "replicate": 3,
        "rng_seed": 20261106,
    }
    ses = ids.session_id_experiment(**spec)
    cases: list[dict[str, Any]] = [
        {"id": "session-experiment", "op": "session_experiment", "input": spec, "expect": {"result": "accept", "session_id": ses}},
        {
            "id": "session-experiment-replicate-changes-id",
            "op": "session_experiment",
            "input": {**spec, "replicate": 4},
            "expect": {"result": "accept", "session_id": ids.session_id_experiment(**{**spec, "replicate": 4})},
        },
        {
            "id": "session-experiment-negative-seed",
            "op": "session_experiment",
            "input": {**spec, "rng_seed": -1},
            "expect": {"result": "accept", "session_id": ids.session_id_experiment(**{**spec, "rng_seed": -1})},
        },
        {"id": "session-experiment-negative-replicate", "op": "session_experiment", "input": {**spec, "replicate": -1}, "expect": {"result": "reject", "code": "E_ID_INPUT"}},
        {"id": "session-experiment-empty-item", "op": "session_experiment", "input": {**spec, "item_id": ""}, "expect": {"result": "reject", "code": "E_ID_INPUT"}},
        {"id": "session-experiment-seed-too-large", "op": "session_experiment", "input": {**spec, "rng_seed": 2**53}, "expect": {"result": "reject", "code": "E_ID_INPUT"}},
        {"id": "observation-0", "op": "observation_id", "input": {"session_id": ses, "ordinal": 0}, "expect": {"result": "accept", "observation_id": ids.observation_id(ses, 0)}},
        {"id": "observation-1", "op": "observation_id", "input": {"session_id": ses, "ordinal": 1}, "expect": {"result": "accept", "observation_id": ids.observation_id(ses, 1)}},
        {"id": "observation-negative-ordinal", "op": "observation_id", "input": {"session_id": ses, "ordinal": -1}, "expect": {"result": "reject", "code": "E_ID_INPUT"}},
        {"id": "observation-bad-session", "op": "observation_id", "input": {"session_id": "ses:xyz", "ordinal": 0}, "expect": {"result": "reject", "code": "E_ID_INPUT"}},
    ]
    return cases


# ---------------------------------------------------------------- envelopes


def _env(
    *,
    name: str,
    kind: str,
    payload: dict[str, Any],
    seq: int,
    session: str,
    obs: str | None,
    parents: list[dict[str, Any]] | None = None,
    calibration_ref: dict[str, str] | None = None,
    space_id: str | None = "S1",
    policy_refs: list[dict[str, str]] | None = None,
    rule_refs: list[dict[str, str]] | None = None,
    build: str = "build-1",
    version: str = "1.0.0",
) -> dict[str, Any]:
    return {
        "contract": {"id": "IC-00", "version": "0.6.2"},
        "content_id": "cnt:" + "0" * 64,
        "artifact_id": "art:" + "0" * 64,
        "kind": kind,
        "payload_schema": {"id": "test.payload", "version": "1.0.0"},
        "payload": payload,
        "producer": {"name": name, "version": version, "build": build},
        "session_id": session,
        "observation_id": obs,
        "event_span": None,
        "space_id": space_id,
        "parents": parents or [],
        "policy_refs": policy_refs or [],
        "calibration_ref": calibration_ref,
        "rule_refs": rule_refs or [],
        "observed_at": None,
        "seq": seq,
        "produced_at": "2026-11-06T00:00:00Z",
        "extensions": {},
    }


def seal(env: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out = copy.deepcopy(env)
    out["content_id"] = ids.content_id(out, lookup)
    out["artifact_id"] = ids.artifact_id(out, lookup)
    return out


def _stored(env: dict[str, Any]) -> dict[str, Any]:
    return {"content_id": env["content_id"], "observation_id": env["observation_id"], "seq": env["seq"]}


def build_world() -> dict[str, Any]:
    ses = ids.session_id_experiment("sha256:" + "c" * 64, "item-001", "baseline", 0, 7)
    obs0 = ids.observation_id(ses, 0)
    obs1 = ids.observation_id(ses, 1)
    lookup: dict[str, dict[str, Any]] = {}
    world: dict[str, Any] = {"session": ses, "obs0": obs0, "obs1": obs1}

    def add(key: str, env: dict[str, Any]) -> dict[str, Any]:
        sealed = seal(env, lookup)
        world[key] = sealed
        lookup[sealed["artifact_id"]] = _stored(sealed)
        return sealed

    r1 = add("r1", _env(name="nvs-kernel", kind="observation", payload={"n": 1}, seq=1, session=ses, obs=obs0))
    r2 = add("r2", _env(name="nvs-kernel", kind="observation", payload={"n": 2}, seq=2, session=ses, obs=obs0))
    r3 = add("r3", _env(name="nvs-kernel", kind="observation", payload={"n": 3}, seq=3, session=ses, obs=obs1))
    cal = add("cal", _env(name="meaning-space-runtime", kind="interpretation", payload={"calibration": 1}, seq=4, session=ses, obs=None))
    pol_a = {"name": "policy-a", "sha256": "1" * 64}
    pol_b = {"name": "policy-b", "sha256": "2" * 64}
    rule_a = {"name": "rule-a", "version": "1", "sha256": "3" * 64}
    rule_b = {"name": "rule-b", "version": "1", "sha256": "4" * 64}
    ids_unordered = sorted([r1["artifact_id"], r2["artifact_id"]])
    base = _env(
        name="meaning-space-runtime",
        kind="interpretation",
        payload={"mode": "single", "values": [1, 2, 3]},
        seq=10,
        session=ses,
        obs=obs0,
        parents=[
            {"role": "calibration", "ordered": False, "artifact_ids": [cal["artifact_id"]]},
            {"role": "history", "ordered": True, "artifact_ids": [r2["artifact_id"], r1["artifact_id"]]},
            {"role": "trajectory", "ordered": False, "artifact_ids": ids_unordered},
        ],
        calibration_ref={"artifact_id": cal["artifact_id"], "content_id": cal["content_id"]},
        policy_refs=[pol_a, pol_b],
        rule_refs=[rule_a, rule_b],
    )
    base["parents"][2]["artifact_ids"] = ids_unordered
    world["base_unsealed"] = base
    world["base"] = seal(base, lookup)
    world["lookup"] = lookup
    world["extra"] = {"r3": r3}
    return world


def envelope_cases() -> dict[str, Any]:
    w = build_world()
    lookup = w["lookup"]
    base = w["base"]

    def variant(key: str, fn: Any) -> tuple[str, dict[str, Any]]:
        env = copy.deepcopy(base)
        fn(env)
        return key, env

    def swap_policy(e: dict[str, Any]) -> None:
        e["policy_refs"].reverse()

    def swap_rule(e: dict[str, Any]) -> None:
        e["rule_refs"].reverse()

    def swap_unordered(e: dict[str, Any]) -> None:
        e["parents"][2]["artifact_ids"].reverse()

    def swap_ordered(e: dict[str, Any]) -> None:
        e["parents"][1]["artifact_ids"].reverse()

    def swap_roles(e: dict[str, Any]) -> None:
        e["parents"].reverse()

    def set_(path: tuple[str, ...], value: Any) -> Any:
        def fn(e: dict[str, Any]) -> None:
            node = e
            for part in path[:-1]:
                node = node[part]
            node[path[-1]] = value

        return fn

    variants = dict(
        [
            variant("policy_refs_reordered", swap_policy),
            variant("rule_refs_reordered", swap_rule),
            variant("unordered_parents_reordered", swap_unordered),
            variant("roles_reordered", swap_roles),
            variant("ordered_parents_swapped", swap_ordered),
            variant("produced_at_changed", set_(("produced_at",), "2030-01-01T00:00:00Z")),
            variant("seq_changed", set_(("seq",), 99)),
            variant("extensions_changed", set_(("extensions",), {"x-test-note": {"a": 1}})),
            variant(
                "observed_at_changed",
                set_(("observed_at",), {"value": "2026-11-06T00:00:00Z", "precision": "second", "tz": "explicit"}),
            ),
            variant("build_changed", set_(("producer", "build"), "build-2")),
            variant("version_changed", set_(("producer", "version"), "1.0.1")),
            variant("payload_changed", set_(("payload",), {"mode": "single", "values": [1, 2, 4]})),
            variant("session_changed", set_(("session_id",), ids.session_id_experiment("sha256:" + "c" * 64, "item-001", "baseline", 1, 7))),
            variant("observation_id_changed", set_(("observation_id",), w["obs1"])),
            variant("space_id_changed", set_(("space_id",), "S2")),
            variant("event_span_changed", set_(("event_span",), {"token_start": 0, "token_end": 5})),
        ]
    )
    cases = [{"id": "base", "envelope": base}]
    for key, env in variants.items():
        sealed = seal(env, lookup)
        cases.append({"id": key, "envelope": sealed})
    for case in cases:
        env = case["envelope"]
        case["expect"] = {
            "content_id": env["content_id"],
            "artifact_id": env["artifact_id"],
            "envelope_jcs_sha256": sha256_hex(jcs(env)),
        }
        case["input_unsealed_ids"] = True  # ids in `envelope` are the expected ones; recompute and compare
    # The reordered/changed variants must be re-derived from the *unsealed
    # mutation* so a Rust implementation sees the mutated arrays as given:
    mutated = {key: env for key, env in variants.items()}
    for case in cases[1:]:
        case["envelope"] = copy.deepcopy(mutated[case["id"]])
        case["envelope"]["content_id"] = case["expect"]["content_id"]
        case["envelope"]["artifact_id"] = case["expect"]["artifact_id"]
    relations = [
        ("policy_refs_reordered", "same", "same", "policy_refs is a set: array order does not matter"),
        ("rule_refs_reordered", "same", "same", "rule_refs is a set"),
        ("unordered_parents_reordered", "same", "same", "ordered:false roles are sorted by id"),
        ("roles_reordered", "same", "same", "roles are sorted by name"),
        ("ordered_parents_swapped", "differ", "differ", "ordered:true keeps the given order"),
        ("produced_at_changed", "same", "same", "produced_at is not hashed"),
        ("seq_changed", "same", "same", "seq is not hashed"),
        ("extensions_changed", "same", "same", "extensions are not hashed"),
        ("observed_at_changed", "same", "same", "observed_at is not hashed (not in the section 2.1 field lists)"),
        ("build_changed", "same", "differ", "producer.build is in artifact_id only"),
        ("version_changed", "differ", "differ", "producer.version is in content_id"),
        ("payload_changed", "differ", "differ", ""),
        ("session_changed", "same", "differ", "session_id is in artifact_id only"),
        ("observation_id_changed", "same", "differ", "observation_id is in artifact_id only"),
        ("space_id_changed", "differ", "differ", ""),
        ("event_span_changed", "differ", "differ", ""),
    ]
    out_rel = []
    by_id = {c["id"]: c for c in cases}
    for key, content, artifact, note in relations:
        a, b = by_id["base"]["expect"], by_id[key]["expect"]
        assert (a["content_id"] == b["content_id"]) == (content == "same"), key
        assert (a["artifact_id"] == b["artifact_id"]) == (artifact == "same"), key
        out_rel.append({"a": "base", "b": key, "content_id": content, "artifact_id": artifact, "note": note})
    return {"lookup": lookup, "cases": cases, "relations": out_rel, "world": w}


def check_cases() -> dict[str, Any]:
    env = envelope_cases()
    w = env["world"]
    lookup = w["lookup"]
    base = w["base"]
    out: list[dict[str, Any]] = []

    def case(case_id: str, envelope: dict[str, Any], codes: list[str], note: str = "", lk: dict[str, Any] | None = None) -> None:
        use = lookup if lk is None else lk
        got = sorted({v.code for v in check_envelope(envelope, use)})
        assert got == sorted(codes), (case_id, got)
        out.append(
            {
                "id": case_id,
                "note": note,
                "envelope": envelope,
                "lookup": use,
                "expect": {"result": "accept" if not codes else "reject", "codes": sorted(codes)},
            }
        )

    def resealed(mut: Any) -> dict[str, Any]:
        e = copy.deepcopy(w["base_unsealed"])
        mut(e)
        return seal(e, lookup)

    root = w["r1"]
    case("accept-root-observation", root, [], lk={})
    case("accept-derived", base, [])
    case("accept-calibration-artifact", w["cal"], [], lk={})

    bad = copy.deepcopy(base)
    del bad["seq"]
    case("schema-missing-field", bad, ["schema"])
    bad = copy.deepcopy(base)
    bad["content_id"] = "cnt:xyz"
    case("schema-bad-content-id-pattern", bad, ["schema"])
    bad = copy.deepcopy(base)
    bad["extensions"] = {"note": 1}
    case("schema-extension-key-without-x-prefix", bad, ["schema"])
    bad = copy.deepcopy(base)
    bad["unexpected"] = 1
    case("schema-additional-property", bad, ["schema"])
    bad = copy.deepcopy(base)
    bad["kind"] = "belief"
    case("schema-kind-not-in-d70", bad, ["schema"])
    bad = copy.deepcopy(base)
    bad["parents"][0]["artifact_ids"] = []
    case("schema-empty-parent-role", bad, ["schema"])
    bad = copy.deepcopy(base)
    bad["seq"] = 2**53
    case("schema-seq-out-of-range", bad, ["schema"])
    bad = copy.deepcopy(base)
    bad["observed_at"] = {"value": "2026-11-06", "precision": "day"}
    case("schema-observed-at-missing-tz", bad, ["schema"])
    bad = copy.deepcopy(base)
    bad["produced_at"] = "yesterday"
    case("schema-produced-at-not-rfc3339", bad, ["schema"])

    sel = resealed(lambda e: e.update(kind="selection"))
    case("S4-msr-cannot-produce-selection", sel, ["S4"])
    unk = resealed(lambda e: e["producer"].update(name="mystery-tool"))
    case("S4-unknown-producer", unk, ["S4"])
    hk = copy.deepcopy(root)
    hk["producer"]["name"] = "sensos-ux"
    hk["kind"] = "selection"
    hk = seal(hk, {})
    case("accept-hanko-selection", hk, [], lk={})
    hk2 = copy.deepcopy(root)
    hk2["producer"]["name"] = "hekb-vnext"
    hk2["kind"] = "interpretation"
    case("S4-hekb-cannot-produce-interpretation", seal(hk2, {}), ["S4"], lk={})
    ad = copy.deepcopy(root)
    ad["producer"]["name"] = "adapter:carry-evidence"
    ad["kind"] = "interpretation"
    ad["observation_id"] = None
    case("accept-adapter-prefix", seal(ad, {}), [], lk={})

    case("S16-policy-refs-unsorted", env["cases"][1]["envelope"], ["S16"], "policy_refs given in reverse order; ids still equal (they sort)")
    case("S16-rule-refs-unsorted", env["cases"][2]["envelope"], ["S16"])
    case("S16-unordered-ids-unsorted", env["cases"][3]["envelope"], ["S16"])
    case("S16-roles-unsorted", env["cases"][4]["envelope"], ["S16"])
    dup = copy.deepcopy(w["base_unsealed"])
    dup["policy_refs"] = [dup["policy_refs"][0], dup["policy_refs"][0]]
    dup["content_id"], dup["artifact_id"] = base["content_id"], base["artifact_id"]
    case("S16-duplicate-policy-ref", dup, ["S16"])
    dup = copy.deepcopy(base)
    dup["parents"][2]["artifact_ids"] = [dup["parents"][2]["artifact_ids"][0]] * 2
    case("S16-duplicate-parent-id", dup, ["S16"])
    dup = copy.deepcopy(base)
    dup["parents"].append(copy.deepcopy(dup["parents"][2]))
    case("S16-duplicate-role", dup, ["S16"])
    case("accept-ordered-role-keeps-given-order", env["cases"][5]["envelope"], [], "ordered:true role swapped; ids recomputed, so valid")

    partial = {k: v for k, v in lookup.items() if k != w["r1"]["artifact_id"]}
    case("parent-unknown", base, ["parent_unknown"], lk=partial)
    nocal = {k: v for k, v in lookup.items() if k != w["cal"]["artifact_id"]}
    case("calibration-unknown", base, ["parent_unknown", "calibration_unknown"], lk=nocal)
    wrong = copy.deepcopy(base)
    wrong["calibration_ref"]["content_id"] = "cnt:" + "9" * 64
    case("calibration-content-id-mismatch", wrong, ["calibration_mismatch", "content_id_mismatch", "artifact_id_mismatch"])

    tampered = copy.deepcopy(base)
    tampered["payload"] = {"mode": "single", "values": [9]}
    case("content-id-mismatch-payload-tampered", tampered, ["content_id_mismatch", "artifact_id_mismatch"])
    tampered = copy.deepcopy(base)
    tampered["producer"]["build"] = "build-tampered"
    case("artifact-id-mismatch-build-tampered", tampered, ["artifact_id_mismatch"])
    tampered = copy.deepcopy(base)
    tampered["artifact_id"] = "art:" + "0" * 64
    case("artifact-id-mismatch-zeroed", tampered, ["artifact_id_mismatch"])

    case("S8-root-observation-without-observation-id", seal({**copy.deepcopy(w["r1"]), "observation_id": None}, {}), ["S8"], lk={})
    case("S8-derived-wrong-observation-id", resealed(lambda e: e.update(observation_id=w["obs1"])), ["S8"])
    r3 = w["extra"]["r3"]
    lookup3 = dict(lookup)
    lookup3[r3["artifact_id"]] = _stored(r3)

    def cross(e: dict[str, Any]) -> None:
        ids_ = sorted([w["r1"]["artifact_id"], r3["artifact_id"]])
        e["parents"] = [{"role": "left_right", "ordered": False, "artifact_ids": ids_}]
        e["calibration_ref"] = None
        e["observation_id"] = None

    cx = copy.deepcopy(w["base_unsealed"])
    cross(cx)
    case("accept-cross-observation-null-observation-id", seal(cx, lookup3), [], lk=lookup3)
    cx2 = copy.deepcopy(cx)
    cx2["observation_id"] = w["obs0"]
    case("S8-cross-observation-must-be-null", seal(cx2, lookup3), ["S8"], lk=lookup3)

    case("S5-parent-seq-equal", resealed(lambda e: e.update(seq=4)), ["S5"], "seq 4 equals the calibration artifact's seq")
    case("S5-parent-seq-later", resealed(lambda e: e.update(seq=1)), ["S5"])
    return {"cases": out}


# --------------------------------------------------------------------- main


def _dump(name: str, doc: dict[str, Any]) -> None:
    VECTORS.mkdir(parents=True, exist_ok=True)
    (VECTORS / name).write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def generate() -> dict[str, dict[str, Any]]:
    env = envelope_cases()
    return {
        "canonicalize.json": {
            "format": "canonicalize/1",
            "pipeline": "strict_load(bytes of input) then jcs(); input_utf8 is encoded as UTF-8, input_hex is raw bytes",
            "cases": canonicalize_cases(),
        },
        "quantize.json": {
            "format": "quantize/1",
            "rule": "q = round_ties_to_even(value * 2^(-exponent)); value is the IEEE-754 binary64 whose big-endian bits are value_bits; range envelope=[-(2^53-1), 2^53-1], int64=[-2^63, 2^63-1]",
            "cases": quantize_cases(),
        },
        "ids.json": {"format": "ids/1", "cases": id_cases()},
        "envelope-ids.json": {
            "format": "envelope-ids/1",
            "rule": "content_id and artifact_id of `envelope` (given lookup: artifact_id -> {content_id, observation_id, seq}) must equal expect; `relations` state which ids stay equal between two cases",
            "lookup": env["lookup"],
            "cases": env["cases"],
            "relations": env["relations"],
        },
        "check-envelope.json": {
            "format": "check-envelope/1",
            "rule": "check_envelope(envelope, lookup) returns the set of violation codes in expect.codes (empty = accept)",
            **check_cases(),
        },
    }


def main() -> None:
    for name, doc in generate().items():
        _dump(name, doc)
        print("wrote", name)


if __name__ == "__main__":
    main()
