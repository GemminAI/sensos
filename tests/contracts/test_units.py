"""Branches the vectors do not reach, plus the import boundary of tools/contracts."""

from __future__ import annotations

import ast
import copy
import math
import sys
from pathlib import Path
from typing import Any

import pytest
from contracts import ids
from contracts.check import check_envelope
from contracts.errors import ContractError
from contracts.jcs import jcs
from contracts.quantize import dequantize, quantize
from contracts.strict_load import strict_load
from make_vectors import build_world


def code_of(fn: Any, *args: Any, **kwargs: Any) -> str:
    with pytest.raises(ContractError) as info:
        fn(*args, **kwargs)
    return str(info.value.code)


def test_jcs_python_values() -> None:
    assert code_of(jcs, 1.5) == "E_FLOAT_TYPE"
    assert code_of(jcs, {1: 2}) == "E_NOT_CANONICALIZABLE"
    assert code_of(jcs, object()) == "E_NOT_CANONICALIZABLE"
    assert code_of(jcs, "\ud800") == "E_SURROGATE"
    assert jcs((1, 2)) == b"[1,2]"
    assert jcs({"a": True, "b": False}) == b'{"a":true,"b":false}'


def test_quantize_input_types() -> None:
    assert code_of(quantize, "1", -30) == "E_QUANT_NONFINITE"
    assert code_of(quantize, True, -30) == "E_QUANT_NONFINITE"
    assert quantize(3, 0) == 3  # ints are accepted
    assert code_of(dequantize, 1.5, 0) == "E_QUANT_RANGE"
    assert code_of(dequantize, 2**53, 0) == "E_QUANT_RANGE"
    assert dequantize(3, -30) == 3 * 2.0**-30
    assert dequantize(0, 5) == 0.0
    assert math.copysign(1.0, dequantize(0, 0)) == 1.0


def test_strict_load_accepts_nested_valid_pair_in_key() -> None:
    assert strict_load('{"\\ud83d\\ude00": [1, {"b": null}]}'.encode()) == {"\U0001f600": [1, {"b": None}]}
    assert code_of(strict_load, b'[{"a":"\\ud800"}]') == "E_SURROGATE"
    assert code_of(strict_load, b"[" * 100000) == "E_SYNTAX"


def test_session_ids() -> None:
    assert ids.session_id_operational(b"\x01" * 32) == "ses:" + "01" * 32
    assert ids.session_id_operational().startswith("ses:")
    assert code_of(ids.session_id_operational, b"short") == "E_ID_INPUT"
    assert code_of(ids.session_id_experiment, "h", "i", "c", True, 1) == "E_ID_INPUT"
    assert code_of(ids.observation_id, 5, 0) == "E_ID_INPUT"
    ses = ids.session_id_experiment("h", "i", "c", 0, 1)
    assert ids.observation_id(ses, 0) != ids.observation_id(ses, 1)


def test_content_id_needs_lookup_for_parents() -> None:
    world = build_world()
    base = world["base"]
    assert code_of(ids.content_id, base, None) == "E_LOOKUP"
    assert code_of(ids.content_id, base, {}) == "E_LOOKUP"
    assert code_of(ids.content_id, base, {a: {} for a in world["lookup"]}) == "E_LOOKUP"
    # a root artifact needs no lookup
    root = world["r1"]
    assert ids.content_id(root) == root["content_id"]
    assert ids.artifact_id(root) == root["artifact_id"]


def test_check_envelope_lookup_problems() -> None:
    world = build_world()
    base = world["base"]
    lookup = copy.deepcopy(world["lookup"])
    some = base["parents"][0]["artifact_ids"][0]
    del lookup[some]["content_id"]
    codes = {v.code for v in check_envelope(base, lookup)}
    assert "lookup_incomplete" in codes
    lookup = copy.deepcopy(world["lookup"])
    lookup[some]["seq"] = "x"
    assert "lookup_incomplete" in {v.code for v in check_envelope(base, lookup)}


def test_check_envelope_adapter_and_capability_prefixes() -> None:
    world = build_world()
    cap = copy.deepcopy(world["r1"])
    cap["producer"]["name"] = "capability:fs-read"
    cap["kind"] = "interpretation"
    cap["observation_id"] = None
    sealed = copy.deepcopy(cap)
    sealed["content_id"] = ids.content_id(sealed)
    sealed["artifact_id"] = ids.artifact_id(sealed)
    assert check_envelope(sealed, {}) == []
    sealed["kind"] = "selection"
    assert "S4" in {v.code for v in check_envelope(sealed, {})}


def test_reference_implementation_imports_only_stdlib_and_jsonschema() -> None:
    root = Path(__file__).resolve().parents[2] / "tools" / "contracts"
    allowed_third_party = {"jsonschema", "referencing", "contracts"}
    stdlib = set(sys.stdlib_module_names)
    seen = 0
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                seen += 1
                assert top in stdlib | allowed_third_party | {"__future__"}, (path.name, name)
    assert seen > 20
