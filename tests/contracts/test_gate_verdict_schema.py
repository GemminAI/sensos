"""GateVerdict (gate-verdict/1) schema (U6T-1a): lint, examples, closed objects, the refused forms, the lock."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from contracts.jcs import jcs
from contracts.schemas import CONTRACTS_DIR, load_schema
from jsonschema import Draft202012Validator

SCHEMA_PATH = "nvs/gate-verdict.schema.json"
VECTOR_FILE = CONTRACTS_DIR / "nvs/vectors/gate-verdict.json"
DOC = json.loads(VECTOR_FILE.read_text(encoding="utf-8"))
CASES = {case["id"]: case["verdict"] for case in DOC["cases"]}
LOCK = json.loads(
    Path(__file__).with_name("contract-gate-verdict.lock").read_text(encoding="utf-8")
)
GENERATOR = (
    Path(__file__).resolve().parents[2] / "tools/contracts/make_vectors_gate_verdict.py"
)
TOP_KEYS = (
    "verdict_version",
    "subject",
    "result",
    "layers",
    "codes",
    "violations",
    "unverifiable",
    "waived",
    "rules",
    "inputs",
    "gate",
    "produced_by",
    "verdict_sha256",
)

VALIDATOR = Draft202012Validator(load_schema(SCHEMA_PATH))


def first_path(verdict: Any) -> str | None:
    errors = sorted(VALIDATOR.iter_errors(verdict), key=lambda e: list(e.absolute_path))
    return "/".join(str(x) for x in errors[0].absolute_path) if errors else None


def accepted(verdict: Any) -> bool:
    return not list(VALIDATOR.iter_errors(verdict))


def case(name: str) -> dict[str, Any]:
    return copy.deepcopy(CASES[name])


# -------------------------------------------------------------------------------------- the schema


def test_schema_lint_and_id() -> None:
    schema = load_schema(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == "sensos:contracts/nvs/gate-verdict/1"
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert tuple(schema["required"]) == TOP_KEYS and set(schema["properties"]) == set(
        TOP_KEYS
    )
    assert "D-185 (9)" in schema["description"] and "DC-T1-2" in schema["description"]


def _objects(node: Any, where: str = "#") -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            found.append((where, node))
        for key, value in node.items():
            if key in ("properties", "$defs", "patternProperties"):
                for name, sub in value.items():
                    found += _objects(sub, f"{where}/{key}/{name}")
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
                    found += _objects(sub, f"{where}/{key}/{i}")
    return found


def test_every_object_is_closed() -> None:
    objects = _objects(load_schema(SCHEMA_PATH))
    assert len(objects) >= 18
    assert [
        w for w, node in objects if node.get("additionalProperties") is not False
    ] == []


def test_no_eligibility_no_admission_no_time() -> None:
    text = json.dumps(load_schema(SCHEMA_PATH)["properties"])
    for word in (
        "eligib",
        "admit",
        "admission",
        "chain",
        "created_at",
        "produced_at",
        "timestamp",
    ):
        assert word not in text.lower().replace("verdict_version", "")
    assert set(load_schema(SCHEMA_PATH)["properties"]["produced_by"]["properties"]) == {
        "name",
        "version",
        "build",
    }


# ------------------------------------------------------------------------------------- the examples


def test_there_are_pass_unverified_fail_l1_fail_l2_and_window_examples() -> None:
    assert set(CASES) >= {
        "pass",
        "pass-unverified",
        "fail-l1",
        "fail-l2",
        "pass-unverified-window",
    }
    assert {CASES[n]["result"] for n in CASES} == {"PASS", "PASS_UNVERIFIED", "FAIL"}
    assert len(CASES) >= 4


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_example_is_accepted(name: str) -> None:
    assert first_path(CASES[name]) is None


@pytest.mark.parametrize("name", sorted(CASES))
def test_verdict_sha256_of_every_example_is_the_jcs_of_the_rest(name: str) -> None:
    verdict = CASES[name]
    body = {k: v for k, v in verdict.items() if k != "verdict_sha256"}
    assert verdict["verdict_sha256"] == hashlib.sha256(jcs(body)).hexdigest()


def test_waived_is_empty_in_every_example() -> None:
    assert all(v["waived"] == [] for v in CASES.values())


def test_an_l1_failure_leaves_l2_and_l3_not_run() -> None:
    layers = CASES["fail-l1"]["layers"]
    assert layers["L1"] == {"status": "FAIL", "codes": ["S8"]}
    assert layers["L2"]["status"] == "not_run" and layers["L2"]["kind"] is None
    assert layers["L3"]["status"] == "not_run"


# ----------------------------------------------------------------------------- what is refused


@pytest.mark.parametrize("name", sorted(CASES))
def test_an_extra_key_is_refused_at_every_level(name: str) -> None:
    verdict = case(name)
    verdict["extra"] = 1
    assert first_path(verdict) == ""
    for where in ("subject", "layers", "rules", "inputs", "gate", "produced_by"):
        verdict = case(name)
        verdict[where]["extra"] = 1
        assert first_path(verdict) == where
    verdict = case(name)
    verdict["gate"]["checker"]["extra"] = 1
    assert first_path(verdict) == "gate/checker"
    verdict = case(name)
    verdict["gate"]["checker"]["files"][0]["extra"] = 1
    assert first_path(verdict) == "gate/checker/files/0"
    verdict = case(name)
    verdict["gate"]["runtime"]["platform"]["extra"] = 1
    assert first_path(verdict) == "gate/runtime/platform"


@pytest.mark.parametrize("key", TOP_KEYS)
def test_a_missing_top_level_key_is_refused(key: str) -> None:
    verdict = case("pass")
    del verdict[key]
    assert not accepted(verdict)


@pytest.mark.parametrize(
    ("where", "key"),
    [
        ("subject", "envelope_sha256"),
        ("layers", "L3"),
        ("rules", "payload_schema"),
        ("inputs", "contract_facts_sha256"),
        ("inputs", "lookup_sha256"),
        ("gate", "unverifiable_catalog"),
        ("gate", "runtime"),
        ("produced_by", "build"),
    ],
)
def test_a_missing_nested_key_is_refused(where: str, key: str) -> None:
    verdict = case("pass")
    del verdict[where][key]
    assert not accepted(verdict)


def test_a_missing_key_inside_a_layer_a_violation_or_an_unverifiable_is_refused() -> (
    None
):
    verdict = case("pass")
    del verdict["layers"]["L2"]["kind"]
    assert not accepted(verdict)
    verdict = case("fail-l2")
    del verdict["violations"][0]["message"]
    assert not accepted(verdict)
    verdict = case("pass-unverified")
    del verdict["unverifiable"][0]["layer"]
    assert not accepted(verdict)


def test_waived_as_a_result_is_refused() -> None:
    verdict = case("fail-l2")
    verdict["result"] = "WAIVED"
    assert first_path(verdict) == "result"


def test_a_waived_entry_is_refused() -> None:
    verdict = case("fail-l2")
    verdict["waived"] = [{"code": "E_TRAJ_SYNTHETIC", "reason": "x"}]
    assert first_path(verdict) == "waived"


def test_the_result_must_follow_the_violations_and_the_unverifiable() -> None:
    wrong = case("fail-l2")
    wrong["result"] = "PASS"
    assert not accepted(wrong)
    wrong = case("pass-unverified")
    wrong["result"] = "PASS"
    assert not accepted(wrong)
    wrong = case("pass")
    wrong["result"] = "PASS_UNVERIFIED"
    assert not accepted(wrong)
    wrong = case("pass")
    wrong["result"] = "FAIL"
    assert not accepted(wrong)
    wrong = case("fail-l2")
    wrong["unverifiable"] = [
        {"layer": "L2", "check": "points_bytes", "reason": "blob_not_supplied"}
    ]
    wrong["result"] = "PASS_UNVERIFIED"
    assert not accepted(wrong)


def test_l2_and_l3_must_be_not_run_when_l1_fails() -> None:
    verdict = case("fail-l1")
    verdict["layers"]["L2"]["status"] = "PASS"
    verdict["layers"]["L2"]["kind"] = "hidden_trajectory"
    assert not accepted(verdict)
    verdict = case("fail-l1")
    verdict["layers"]["L3"]["status"] = "not_applicable"
    assert not accepted(verdict)
    verdict = case("pass")
    verdict["layers"]["L2"] = {"status": "not_run", "kind": None, "codes": []}
    assert not accepted(verdict)  # an L1 that passed leaves L2 run


def test_l1_status_is_pass_or_fail_only() -> None:
    verdict = case("pass")
    verdict["layers"]["L1"]["status"] = "PASS_UNVERIFIED"
    assert not accepted(verdict)
    verdict["layers"]["L1"]["status"] = "not_run"
    assert not accepted(verdict)


def test_l2_kind_is_null_exactly_when_not_run() -> None:
    verdict = case("pass")
    verdict["layers"]["L2"]["kind"] = None
    assert not accepted(verdict)
    verdict["layers"]["L2"]["kind"] = "other"
    assert not accepted(verdict)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("verdict_version",), "gate-verdict/2"),
        (("subject", "artifact_id"), "cnt:" + "0" * 64),
        (("subject", "content_id"), "art:" + "0" * 64),
        (("subject", "envelope_sha256"), "A" * 64),
        (("verdict_sha256",), "0" * 63),
        (("inputs", "lookup_sha256"), "xyz"),
        (("inputs", "contract_facts_sha256"), "0" * 10),
        (("gate", "checker", "bundle_sha256"), ""),
        (("gate", "checker", "sensos_commit"), "4cdb968"),
        (("rules", "ic00_contract_version"), "1.1"),
        (("gate", "runtime", "python"), ""),
        (("gate", "unverifiable_catalog", "version"), ""),
        (("produced_by", "name"), ""),
    ],
)
def test_a_malformed_value_is_refused(path: tuple[str, ...], value: Any) -> None:
    verdict = case("pass")
    node = verdict
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    assert not accepted(verdict)


def test_a_lookup_entry_must_be_complete_and_keyed_by_an_artifact_id() -> None:
    verdict = case("pass")
    key = next(iter(verdict["inputs"]["lookup"]))
    verdict["inputs"]["lookup"][key]["seq"] = -1
    assert not accepted(verdict)
    verdict = case("pass")
    del verdict["inputs"]["lookup"][key]["observation_id"]
    assert not accepted(verdict)
    verdict = case("pass")
    verdict["inputs"]["lookup"]["not-an-id"] = verdict["inputs"]["lookup"][key]
    assert not accepted(verdict)


def test_the_two_commits_may_be_null_and_the_facts_hash_may_be_null() -> None:
    verdict = case("pass")
    verdict["gate"]["checker"]["sensos_commit"] = None
    verdict["inputs"]["contract_facts_sha256"] = None
    assert accepted(verdict)


def test_the_layer_of_an_unverifiable_row_is_l2_or_l3() -> None:
    verdict = case("pass-unverified")
    verdict["unverifiable"][0]["layer"] = "L1"
    assert not accepted(verdict)


# ------------------------------------------------------------------------- generator and lock


def test_the_generator_reproduces_the_example_file(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("mv_gate_verdict_copy", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = tmp_path / "out.json"
    vars(module)["OUT"] = out
    module.main()
    assert out.read_bytes() == VECTOR_FILE.read_bytes()
    assert VECTOR_FILE.read_bytes().endswith(b"}\n")


def test_the_lock_matches_the_schema_file() -> None:
    entry = LOCK["schemas"][0]
    assert LOCK["contract_id"] == "nvs/gate-verdict" and len(LOCK["schemas"]) == 1
    assert entry["path"] == SCHEMA_PATH
    assert entry["id"] == load_schema(SCHEMA_PATH)["$id"]
    assert (
        entry["sha256"]
        == hashlib.sha256((CONTRACTS_DIR / SCHEMA_PATH).read_bytes()).hexdigest()
    )


def test_the_schema_has_no_ref_outside_itself() -> None:
    refs: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref":
                    refs.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(load_schema(SCHEMA_PATH))
    assert refs and all(ref.startswith("#/$defs/") for ref in refs)
