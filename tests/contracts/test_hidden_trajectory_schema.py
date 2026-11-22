"""nvs.hidden-trajectory 0.1.0 payload schema (U5-3): lint, vectors, determinism, lock, $ref and the registry."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from contracts.errors import ContractError
from contracts.hidden_trajectory_registry import (
    HIDDEN_TRAJECTORY_PATHS,
    hidden_trajectory_registry,
    hidden_trajectory_validator,
)
from contracts.schemas import CONTRACTS_DIR, SCHEMA_PATHS, load_schema, registry
from contracts.strict_load import strict_load
from jsonschema import Draft202012Validator

SCHEMA_PATH = "nvs/hidden-trajectory.schema.json"
VECTOR_FILE = CONTRACTS_DIR / "nvs/vectors/hidden-trajectory-payload.json"
DOC = json.loads(VECTOR_FILE.read_text(encoding="utf-8"))
CASES = DOC["cases"]
LOCK = json.loads(
    Path(__file__)
    .with_name("contract-hidden-trajectory.lock")
    .read_text(encoding="utf-8")
)
GENERATOR = (
    Path(__file__).resolve().parents[2]
    / "tools/contracts/make_vectors_hidden_trajectory.py"
)
REQUIRED = (
    "source",
    "position",
    "point",
    "kind",
    "layer",
    "length",
    "dimension",
    "points",
    "token_index",
    "raw_ref",
    "row_rule",
    "binding",
    "final_norm_applied",
    "state_dtype",
    "model_build_id",
    "compute_environment",
    "policy",
    "capture_provenance",
    "contract_ref",
    "unknowns",
)


def _first_path(payload: dict[str, Any]) -> str | None:
    errors = sorted(
        hidden_trajectory_validator(SCHEMA_PATH).iter_errors(payload),
        key=lambda e: list(e.absolute_path),
    )
    return "/".join(str(x) for x in errors[0].absolute_path) if errors else None


# ------------------------------------------------------------------------------------------- the schema


def test_schema_lint_and_id() -> None:
    schema = load_schema(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == "sensos:contracts/nvs/hidden-trajectory/0.1.0"
    assert tuple(schema["required"]) == REQUIRED and len(REQUIRED) == 20
    assert set(schema["properties"]) == set(REQUIRED)
    assert "D-179" in schema["description"] and "HT-04" in schema["description"]


def _objects(node: Any, where: str = "#") -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            out.append((where, node))
        for key, value in node.items():
            if key in ("properties", "$defs"):
                for name, sub in value.items():
                    out += _objects(sub, f"{where}/{key}/{name}")
            elif key in (
                "items",
                "allOf",
                "oneOf",
                "anyOf",
                "if",
                "then",
                "else",
                "not",
            ):
                subs = value if isinstance(value, list) else [value]
                for i, sub in enumerate(subs):
                    out += _objects(sub, f"{where}/{key}/{i}")
    return out


def test_every_nested_object_is_closed() -> None:
    objects = _objects(load_schema(SCHEMA_PATH))
    assert (
        len(objects) >= 8
    )  # payload, raw_ref, binding, policy, capture_provenance, capture, runtime, contract_ref, unknowns item
    open_ones = [
        where
        for where, node in objects
        if node.get("additionalProperties") is not False
    ]
    # runtime is the one object that takes more keys, but only strings (design 3.3: {"backend", ...})
    assert open_ones == ["#/properties/capture_provenance/properties/runtime"]
    runtime = load_schema(SCHEMA_PATH)["properties"]["capture_provenance"][
        "properties"
    ]["runtime"]
    assert runtime["additionalProperties"] == {"type": "string"} and runtime[
        "required"
    ] == ["backend"]


def test_layer_is_a_number_or_final_norm_and_nothing_else() -> None:
    layer = load_schema(SCHEMA_PATH)["properties"]["layer"]
    assert layer["oneOf"][0]["type"] == "integer" and layer["oneOf"][1] == {
        "const": "final_norm"
    }


# --------------------------------------------------------------------------------------------- vectors


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_vectors_replay(case: dict[str, Any]) -> None:
    found = _first_path(case["payload"])
    assert found == case["expect"]["path"]
    assert (found is None) == (case["expect"]["result"] == "accept")


def test_vector_counts_and_required_fields_are_all_covered() -> None:
    accepts = [c for c in CASES if c["expect"]["result"] == "accept"]
    rejects = [c for c in CASES if c["expect"]["result"] == "reject"]
    assert len(accepts) >= 6 and len(rejects) >= 40
    assert all(c["id"].startswith("reject-") for c in rejects)
    ids = {c["id"] for c in rejects}
    for name in REQUIRED:
        assert f"reject-missing-{name}" in ids
    by_id = {c["id"]: c for c in CASES}
    for name in REQUIRED:
        assert name not in by_id[f"reject-missing-{name}"]["payload"]
        assert set(by_id[f"reject-missing-{name}"]["payload"]) == set(REQUIRED) - {name}


def test_the_six_required_accepts_are_present() -> None:
    ids = {c["id"] for c in CASES if c["expect"]["result"] == "accept"}
    assert {
        "accept-llama-final-norm",
        "accept-qwen35-block-out-15",
        "accept-qwen35-mlp-out-15",
        "accept-partly-unknown-provenance",
        "accept-contract-ref-null",
        "accept-chat-template-not-applicable",
    } <= ids


def test_accepts_have_the_documented_shape() -> None:
    by_id = {c["id"]: c["payload"] for c in CASES}
    assert by_id["accept-llama-final-norm"]["layer"] == "final_norm"
    assert by_id["accept-llama-final-norm"]["final_norm_applied"] is True
    assert by_id["accept-llama-final-norm"]["row_rule"] == "llama31-mlx-final-norm/1"
    assert by_id["accept-qwen35-block-out-15"]["layer"] == 15
    assert by_id["accept-qwen35-block-out-15"]["row_rule"] == "qwen35-mlx-block-out/1"
    assert by_id["accept-qwen35-mlp-out-15"]["final_norm_applied"] is False
    assert by_id["accept-contract-ref-null"]["contract_ref"] is None
    assert (
        by_id["accept-chat-template-not-applicable"]["capture_provenance"][
            "chat_template_sha256"
        ]
        == "not_applicable"
    )
    unknown = by_id["accept-partly-unknown-provenance"]
    assert (
        unknown["capture_provenance"]["weights_sha256"] == "unknown"
        and unknown["state_dtype"] == "unknown"
    )
    assert [u["field"] for u in unknown["unknowns"]] == [
        "/capture_provenance/weights_sha256",
        "/state_dtype",
    ]


def test_blobs_are_the_bytes_the_references_name() -> None:
    blobs = {u: bytes.fromhex(h) for u, h in DOC["blobs"].items()}
    for case in (c for c in CASES if c["expect"]["result"] == "accept"):
        payload = case["payload"]
        for field, size in (("points", 48), ("token_index", 24)):
            ref = payload[field]
            assert ref["uri"] == "blob:sha256:" + ref["sha256"]
            assert hashlib.sha256(blobs[ref["uri"]]).hexdigest() == ref["sha256"]
            assert len(blobs[ref["uri"]]) == size
        assert payload["raw_ref"]["trajectory_id"] == payload["points"]["sha256"]
        assert (
            payload["policy"]["sha256"]
            == hashlib.sha256(payload["policy"]["name"].encode()).hexdigest()
        )
        assert (
            payload["length"],
            payload["dimension"],
            payload["binding"]["n_gen"],
        ) == (3, 4, 3)


def test_float_cases_are_accepted_by_the_schema_and_refused_by_the_strict_loader() -> (
    None
):
    assert [c["id"] for c in DOC["float_cases"]] == [
        "float-layer-15-point-0",
        "float-dimension-4-point-0",
    ]
    for case in DOC["float_cases"]:
        assert (
            _first_path(case["payload"]) is None
        )  # JSON Schema 2020-12: 15.0 is an integer
        with pytest.raises(ContractError):
            strict_load(json.dumps(case["payload"]).encode())


# ------------------------------------------------------------------------------------------ determinism


def test_generator_output_is_byte_identical_to_the_saved_vectors(
    tmp_path: Path,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "mv_hidden_trajectory_copy", GENERATOR
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = tmp_path / "out.json"
    vars(module)["OUT"] = out  # main() reads the module global at call time
    module.main()
    assert out.read_bytes() == VECTOR_FILE.read_bytes()
    assert VECTOR_FILE.read_bytes().endswith(b"}\n")


# ------------------------------------------------------------------------------------------------ lock


def test_lock_matches_schema() -> None:
    assert LOCK["contract_id"] == "nvs/hidden-trajectory" and LOCK["version"] == "0.1.0"
    (entry,) = LOCK["schemas"]
    path = CONTRACTS_DIR / entry["path"]
    assert entry["path"] == SCHEMA_PATH
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    assert json.loads(path.read_text(encoding="utf-8"))["$id"] == entry["id"]


# ----------------------------------------------------------------------------------- $ref and registry


def test_points_ref_resolves_to_the_float32_blob_contract() -> None:
    assert load_schema(SCHEMA_PATH)["properties"]["points"] == {
        "$ref": "sensos:contracts/common/float32-blob/0.1.0"
    }
    base = next(c["payload"] for c in CASES if c["id"] == "accept-qwen35-mlp-out-15")
    check = hidden_trajectory_validator(SCHEMA_PATH)
    assert list(check.iter_errors(base)) == []
    assert [
        e.message
        for e in check.iter_errors(
            {**base, "points": {**base["points"], "dtype": "float64"}}
        )
    ]
    bad = {**base, "points": {**base["points"], "dtype": "float64"}}
    assert _first_path(bad) == "points/dtype"


SCHEMAS_PY = Path(__file__).resolve().parents[2] / "tools/contracts/schemas.py"
SCHEMAS_PY_SHA256 = "36b63eb54bc59b59a208058369f2eb81a3aaddfeaa5da11ec71f79263b9691c6"


def test_existing_registry_does_not_contain_the_new_schemas_and_schemas_py_is_unchanged() -> (
    None
):
    # schemas.py is pinned by contract-ic02-v0100.lock; this contract has its own registry module.
    assert hashlib.sha256(SCHEMAS_PY.read_bytes()).hexdigest() == SCHEMAS_PY_SHA256
    assert not set(HIDDEN_TRAJECTORY_PATHS) & set(SCHEMA_PATHS)
    reg = registry()
    for rel in HIDDEN_TRAJECTORY_PATHS:
        assert reg.get(load_schema(rel)["$id"]) is None


def test_hidden_trajectory_registry_has_both_schemas_and_resolves_the_refs() -> None:
    assert HIDDEN_TRAJECTORY_PATHS == (
        "common/float32-blob.schema.json",
        "nvs/hidden-trajectory.schema.json",
    )
    reg = hidden_trajectory_registry()
    for rel in HIDDEN_TRAJECTORY_PATHS:
        assert reg.get(load_schema(rel)["$id"]) is not None
    resolver = reg.resolver()
    float32 = resolver.lookup("sensos:contracts/common/float32-blob/0.1.0").contents
    assert float32["properties"]["dtype"] == {"const": "float32"}
    int_blob = resolver.lookup(
        "sensos:contracts/common/blob/0.7.0#/$defs/intBlob"
    ).contents
    assert int_blob["properties"]["dtype"]  # the intBlob $ref of token_index resolves
    token_index = load_schema(SCHEMA_PATH)["properties"]["token_index"]
    assert token_index["allOf"][0] == {
        "$ref": "sensos:contracts/common/blob/0.7.0#/$defs/intBlob"
    }
    base = next(c["payload"] for c in CASES if c["id"] == "accept-qwen35-mlp-out-15")
    check = hidden_trajectory_validator(SCHEMA_PATH)
    assert (
        _first_path(
            {**base, "token_index": {**base["token_index"], "dtype": "float32"}}
        )
        == "token_index/dtype"
    )
    assert list(check.iter_errors(base)) == []
