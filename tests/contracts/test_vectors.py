"""Every language-neutral vector must pass the reference implementation, and
the checked-in vector files must equal what make_vectors.py generates."""

from __future__ import annotations

import hashlib
import json
import struct
from typing import Any

import pytest
from contracts import ids
from contracts.check import check_envelope
from contracts.errors import ContractError
from contracts.jcs import jcs
from contracts.quantize import ENVELOPE_RANGE, INT64_RANGE, dequantize, quantize
from contracts.strict_load import strict_load
from make_vectors import VECTORS, generate, vector_path


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((VECTORS / name).read_text(encoding="utf-8"))
    return data


def _input_bytes(case: dict[str, Any]) -> bytes:
    if "input_hex" in case:
        return bytes.fromhex(case["input_hex"])
    return str(case["input_utf8"]).encode("utf-8")


CANON = _load("canonicalize.json")["cases"]


@pytest.mark.parametrize("case", CANON, ids=[c["id"] for c in CANON])
def test_canonicalize_vectors(case: dict[str, Any]) -> None:
    expect = case["expect"]
    if expect["result"] == "reject":
        with pytest.raises(ContractError) as info:
            jcs(strict_load(_input_bytes(case)))
        assert info.value.code == expect["code"]
        return
    out = jcs(strict_load(_input_bytes(case)))
    assert out == expect["jcs_utf8"].encode("utf-8")
    assert hashlib.sha256(out).hexdigest() == expect["jcs_sha256"]


QUANT = _load("quantize.json")["cases"]


@pytest.mark.parametrize("case", QUANT, ids=[c["id"] for c in QUANT])
def test_quantize_vectors(case: dict[str, Any]) -> None:
    value = struct.unpack(">d", bytes.fromhex(case["value_bits"]))[0]
    rng = INT64_RANGE if case["range"] == "int64" else ENVELOPE_RANGE
    expect = case["expect"]
    if expect["result"] == "reject":
        with pytest.raises(ContractError) as info:
            quantize(value, case["exponent"], int_range=rng)
        assert info.value.code == expect["code"]
        return
    q = quantize(value, case["exponent"], int_range=rng)
    assert q == expect["q"]
    # dequantize(q) is within half a quantum of the input (exact for ties/grid points)
    back = dequantize(q, case["exponent"], int_range=rng)
    assert abs(back - value) <= 2.0 ** (case["exponent"] - 1)


IDS = _load("ids.json")["cases"]


@pytest.mark.parametrize("case", IDS, ids=[c["id"] for c in IDS])
def test_id_vectors(case: dict[str, Any]) -> None:
    fn = {
        "session_experiment": lambda i: ids.session_id_experiment(**i),
        "observation_id": lambda i: ids.observation_id(i["session_id"], i["ordinal"]),
    }[case["op"]]
    expect = case["expect"]
    if expect["result"] == "reject":
        with pytest.raises(ContractError) as info:
            fn(case["input"])
        assert info.value.code == expect["code"]
        return
    assert fn(case["input"]) == next(v for k, v in expect.items() if k != "result")


ENV = _load("envelope-ids.json")
ENV_BY_ID = {c["id"]: c for c in ENV["cases"]}


@pytest.mark.parametrize("case", ENV["cases"], ids=[c["id"] for c in ENV["cases"]])
def test_envelope_id_vectors(case: dict[str, Any]) -> None:
    env = case["envelope"]
    assert ids.content_id(env, ENV["lookup"]) == case["expect"]["content_id"]
    assert ids.artifact_id(env, ENV["lookup"]) == case["expect"]["artifact_id"]
    assert hashlib.sha256(jcs(env)).hexdigest() == case["expect"]["envelope_jcs_sha256"]


@pytest.mark.parametrize("rel", ENV["relations"], ids=[r["b"] for r in ENV["relations"]])
def test_envelope_relations(rel: dict[str, Any]) -> None:
    a, b = ENV_BY_ID[rel["a"]]["expect"], ENV_BY_ID[rel["b"]]["expect"]
    assert (a["content_id"] == b["content_id"]) == (rel["content_id"] == "same")
    assert (a["artifact_id"] == b["artifact_id"]) == (rel["artifact_id"] == "same")


CHECK = _load("check-envelope.json")["cases"]


@pytest.mark.parametrize("case", CHECK, ids=[c["id"] for c in CHECK])
def test_check_envelope_vectors(case: dict[str, Any]) -> None:
    codes = sorted({v.code for v in check_envelope(case["envelope"], case["lookup"])})
    assert codes == case["expect"]["codes"]
    assert (not codes) == (case["expect"]["result"] == "accept")


def test_vector_counts_are_meaningful() -> None:
    accepts = sum(1 for c in CANON if c["expect"]["result"] == "accept")
    assert accepts >= 10 and len(CANON) - accepts >= 25
    assert sum(1 for c in CHECK if c["expect"]["result"] == "reject") >= 25


def test_vector_files_match_generator() -> None:
    for name, doc in generate().items():
        on_disk = json.loads(vector_path(name).read_text(encoding="utf-8"))
        assert on_disk == json.loads(json.dumps(doc)), f"{name} is stale: rerun tools/contracts/make_vectors.py"
