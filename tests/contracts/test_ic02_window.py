"""IC-02 0.9.0 (D-129): the first-128-rows window.

New tests only; no existing test file is parametrized over anything added here (the window schema is
kept out of ``SCHEMA_PATHS`` for that reason, so this file applies the same lint to it).
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from contracts import ic02_window as W
from contracts.gate import PAYLOAD_SCHEMAS, check_payload
from contracts.ic00_versions import check_envelope_versioned
from contracts.schemas import CONTRACTS_DIR, IC02_V090_PATHS, load_schema, validator
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
VEC = json.loads((CONTRACTS_DIR / "msr/vectors/window.json").read_text(encoding="utf-8"))
BLOBS = {u: bytes.fromhex(h) for u, h in VEC["blobs"].items()}
CASES = {c["id"]: c for c in VEC["cases"]}
LOCK = json.loads((Path(__file__).with_name("contract-ic02-v090.lock")).read_text(encoding="utf-8"))


def _sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


# ------------------------------------------------------------------ the vectors, replayed

@pytest.mark.parametrize("cid", list(CASES))
def test_vector_case(cid: str) -> None:
    c = CASES[cid]
    ic00 = sorted({v.code for v in check_envelope_versioned(c["envelope"], c["lookup"])})
    payload = sorted({v.code for v in check_payload(c["envelope"], c["stored"], BLOBS)})
    assert (ic00, payload) == (c["expect"]["ic00"], c["expect"]["payload"])
    assert c["expect"]["result"] == ("reject" if ic00 or payload else "accept")


def test_vector_counts_and_the_four_required_kinds() -> None:
    accepts = [c for c in VEC["cases"] if c["expect"]["result"] == "accept"]
    assert (len(VEC["cases"]), len(accepts)) == (47, 6)
    # the four kinds the request names: normal / length is not 128 / reference to the original missing / sha256 differs
    for needed in ("accept-window-first-128", "reject-window-length-127", "reject-window-parents-empty", "reject-window-content-sha256-differs-from-points"):
        assert needed in CASES
    assert {c["target"] for c in VEC["cases"]} == {"window", "measurement"}


def test_every_window_case_ic00_1_1_0_accepts_a_good_window() -> None:
    good = CASES["accept-window-first-128"]["envelope"]
    assert good["contract"]["version"] == "1.1.0"
    assert check_envelope_versioned(good, CASES["accept-window-first-128"]["lookup"]) == []
    assert good["kind"] == "observation" and good["producer"]["name"] == "nvs-runtime"


def test_vectors_regenerate_byte_identically(tmp_path: Path) -> None:
    import make_vectors_window as mv

    original = mv.OUT
    mv.OUT = tmp_path / "window.json"
    try:
        mv.BLOBS.clear()
        mv.main()
        assert mv.OUT.read_bytes() == original.read_bytes()
    finally:
        mv.OUT = original


# ------------------------------------------------------------------ rules the vectors do not fix by themselves

def test_constants_agree_between_code_and_schemas() -> None:
    win = load_schema("msr/trajectory-window.schema.json")["properties"]
    assert win["window"]["properties"]["start"] == {"const": W.WINDOW_START}
    assert win["window"]["properties"]["length"] == {"const": W.WINDOW_LENGTH}
    assert win["window"]["properties"]["rule"] == {"const": W.WINDOW_RULE}
    assert win["policy"]["properties"]["name"] == {"const": W.WINDOW_POLICY}
    assert win["points"]["properties"]["shape"]["prefixItems"][0] == {"const": W.WINDOW_LENGTH}
    scope = load_schema("msr/geometry-measurement.schema.json")["$defs"]["inputScope"]["oneOf"][1]["properties"]
    assert (scope["start"], scope["length"], scope["rule"]) == ({"const": 0}, {"const": 128}, {"const": "prefix_rows"})


def test_known_payload_versions_include_the_window_and_both_geometry_rules() -> None:
    assert PAYLOAD_SCHEMAS[("msr.trajectory-window", "0.9.0")] == "msr/trajectory-window.schema.json"
    assert PAYLOAD_SCHEMAS[("msr.geometry-measurement", "0.9.0")] == "msr/geometry-measurement.schema.json"
    assert PAYLOAD_SCHEMAS[("msr.geometry-measurement", "0.7.1")] == "msr/archive/0.8.0/geometry-measurement.schema.json"
    for ident, version in (("msr.trajectory-window", "0.8.0"), ("msr.trajectory-window", "1.0.0"), ("msr.geometry-measurement", "0.8.0")):
        env = {**copy.deepcopy(CASES["accept-window-first-128"]["envelope"]), "payload_schema": {"id": ident, "version": version}}
        assert {v.code for v in check_payload(env, {}, {})} == {"S39"}


def test_a_0_7_1_measurement_is_never_asked_for_a_window() -> None:
    old = CASES["accept-single-0.7.1-old-rule-no-scope"]
    assert "input_scope" not in old["envelope"]["payload"]
    assert old["expect"]["result"] == "accept"
    # and the 0.9.0 schema never accepts the same payload: no silent reading as the new version
    as_new = copy.deepcopy(old["envelope"])
    as_new["payload_schema"]["version"] = "0.9.0"
    assert {v.code for v in check_payload(as_new, old["stored"], BLOBS)} == {"schema"}


def test_a_window_blob_is_not_accepted_without_its_bytes_being_checked() -> None:
    good = CASES["accept-window-first-128"]
    assert check_payload(good["envelope"], good["stored"], BLOBS) == []
    held = {u: d for u, d in BLOBS.items() if u != good["envelope"]["payload"]["points"]["uri"]}
    # without the bytes the Gate can only check the declaration; it must not invent a pass for the content
    assert check_payload(good["envelope"], good["stored"], held) == []


def test_prefix_matches_for_a_reader_holding_the_raw_rows() -> None:
    env = CASES["accept-window-first-128"]["envelope"]["payload"]
    window = BLOBS[env["points"]["uri"]]
    raw = window + bytes(range(256)) * 3  # the original has more rows after the first 128
    assert W.prefix_matches(window, raw, env["dimension"])
    assert not W.prefix_matches(window, bytes(len(window)) + raw[len(window):], env["dimension"])


# ------------------------------------------------------------------ the new schema gets the lint the others get

@pytest.mark.parametrize("rel", IC02_V090_PATHS)
def test_window_schema_is_valid_and_linted(rel: str) -> None:
    schema = load_schema(rel)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == "sensos:contracts/msr/trajectory-window/0.9.0"

    def walk(node: Any, path: str = "") -> Any:
        if isinstance(node, dict):
            yield path, node
            for k, v in node.items():
                yield from walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk(v, f"{path}/{i}")

    for path, node in walk(schema):
        types = [node["type"]] if isinstance(node.get("type"), str) else list(node.get("type", [])) if isinstance(node.get("type"), list) else []
        if "integer" in types:
            assert ("minimum" in node or "exclusiveMinimum" in node) and ("maximum" in node or "exclusiveMaximum" in node), f"{path}: integer without bounds"
        if "array" in types:
            assert isinstance(node.get("x-sensos-ordered"), bool), f"{path}: missing x-sensos-ordered"


def test_geometry_090_is_the_0_8_0_schema_plus_input_scope_only() -> None:
    old = load_schema("msr/archive/0.8.0/geometry-measurement.schema.json")
    new = load_schema("msr/geometry-measurement.schema.json")
    assert old["$id"].endswith("/0.7.1") and new["$id"].endswith("/0.9.0")
    # pair is untouched; single differs only by input_scope (property, required) and one if/then
    assert old["$defs"]["pair"] == new["$defs"]["pair"]
    o, n = copy.deepcopy(old["$defs"]["single"]), copy.deepcopy(new["$defs"]["single"])
    n["required"].remove("input_scope")
    del n["properties"]["input_scope"]
    assert n["allOf"].pop() == {"if": {"properties": {"input_scope": {"properties": {"kind": {"const": "window"}}}}}, "then": {"properties": {"input_ref": {"properties": {"length": {"const": 128}}}}}}
    assert o == n
    assert {k: v for k, v in old["$defs"].items() if k not in ("single", "pair")} == {k: v for k, v in new["$defs"].items() if k not in ("single", "pair", "inputScope")}


def test_the_archived_0_8_0_schema_is_the_one_the_0_8_0_commit_shipped() -> None:
    shown = subprocess.run(["git", "-C", str(ROOT), "show", "bbc085b:docs/architecture/contracts/msr/geometry-measurement.schema.json"], capture_output=True, check=False)
    if shown.returncode != 0:
        pytest.skip("bbc085b not in the local checkout")
    assert (CONTRACTS_DIR / "msr/archive/0.8.0/geometry-measurement.schema.json").read_bytes() == shown.stdout
    readme = subprocess.run(["git", "-C", str(ROOT), "show", "bbc085b:docs/architecture/contracts/msr/README.md"], capture_output=True, check=False)
    assert (CONTRACTS_DIR / "msr/archive/0.8.0/README.md").read_bytes() == readme.stdout


# ------------------------------------------------------------------ the lock, and what must not change

@pytest.mark.parametrize("entry", LOCK["files"], ids=lambda e: str(e["path"]))
def test_file_matches_the_ic02_0_9_0_lock(entry: dict[str, str]) -> None:
    assert _sha(entry["path"]) == entry["sha256"]


def test_readme_states_fixed_window_and_future_parameters_separately() -> None:
    text = (CONTRACTS_DIR / "msr/README.md").read_text(encoding="utf-8")
    fixed = text.index("### 今回の実装（固定）")
    future = text.index("### 将来の拡張（今回の実装ではない）")
    assert fixed < future
    for needle in ("先頭 128 行", "`prefix_rows`", "窓なしの全長", "`{\"kind\": \"full\"}`", "`source_trajectory`", "`nvs-runtime`"):
        assert needle in text[:future], needle
    assert "位置 `start` と長さ `length` をパラメータにする" in text[future:]
    assert "パラメータ" not in text[fixed:future]  # the fixed part never promises parameters


def test_ic00_1_0_0_freeze_is_byte_identical_to_c82918f() -> None:
    freeze = (CONTRACTS_DIR / "IC-00/1.0.0/FREEZE.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$", freeze, re.M)
    assert len(rows) == 15
    for path, digest in rows:
        assert _sha(path) == digest
        shown = subprocess.run(["git", "-C", str(ROOT), "show", f"c82918f:{path}"], capture_output=True, check=False)
        if shown.returncode != 0:
            pytest.skip("c82918f not in the local checkout")
        assert hashlib.sha256(shown.stdout).hexdigest() == digest, path


def test_ic00_1_1_0_files_are_byte_identical_to_c0064c8() -> None:
    freeze = (CONTRACTS_DIR / "IC-00/1.1.0/FREEZE.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$", freeze, re.M)
    assert rows
    for path, _ in rows:
        shown = subprocess.run(["git", "-C", str(ROOT), "show", f"c0064c8:{path}"], capture_output=True, check=False)
        if shown.returncode != 0:
            pytest.skip("c0064c8 not in the local checkout")
        assert (ROOT / path).read_bytes() == shown.stdout, path
    shown = subprocess.run(["git", "-C", str(ROOT), "show", f"c0064c8:{'docs/architecture/contracts/IC-00/1.1.0/FREEZE.md'}"], capture_output=True, check=False)
    assert (CONTRACTS_DIR / "IC-00/1.1.0/FREEZE.md").read_bytes() == shown.stdout


def test_the_validator_for_the_window_schema_resolves_refs() -> None:
    v = validator("msr/trajectory-window.schema.json")
    case = CASES["accept-window-first-128"]["envelope"]["payload"]
    assert list(v.iter_errors(case)) == []
    bad = copy.deepcopy(case)
    bad["token_index"]["dtype"] = "float32"
    assert list(v.iter_errors(bad))
