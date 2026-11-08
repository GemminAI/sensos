"""IC-02 0.10.0 (D-132): the window with a position and a length.

The determined vectors are replayed against the Gate; the undetermined ones (未規定) are replayed too, but kept apart:
they record this implementation's choice and are not in the lock.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest
from contracts import ic02_window as W
from contracts.gate import PAYLOAD_SCHEMAS, check_payload
from contracts.ic00_versions import check_envelope_versioned
from contracts.schemas import CONTRACTS_DIR, load_schema, validator
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
VECTORS = CONTRACTS_DIR / "msr/vectors"
DET = json.loads((VECTORS / "window-rows.json").read_text(encoding="utf-8"))
UND = json.loads((VECTORS / "window-rows-undetermined.json").read_text(encoding="utf-8"))
LOCK = json.loads(Path(__file__).with_name("contract-ic02-v0100.lock").read_text(encoding="utf-8"))
DET_CASES = {c["id"]: c for c in DET["cases"]}
UND_CASES = {c["id"]: c for c in UND["cases"]}


def _blobs(doc: dict[str, Any]) -> dict[str, bytes]:
    return {u: bytes.fromhex(h) for u, h in doc["blobs"].items()}


def _verdict(c: dict[str, Any], doc: dict[str, Any]) -> tuple[list[str], list[str]]:
    return (sorted({v.code for v in check_envelope_versioned(c["envelope"], c["lookup"])}),
            sorted({v.code for v in check_payload(c["envelope"], c["stored"], _blobs(doc))}))


@pytest.mark.parametrize("cid", list(DET_CASES))
def test_determined_case(cid: str) -> None:
    c = DET_CASES[cid]
    assert _verdict(c, DET) == (c["expect"]["ic00"], c["expect"]["payload"])
    assert c["expect"]["result"] == ("reject" if c["expect"]["ic00"] or c["expect"]["payload"] else "accept")


@pytest.mark.parametrize("cid", list(UND_CASES))
def test_undetermined_case_records_the_implementations_behaviour(cid: str) -> None:
    c = UND_CASES[cid]
    assert _verdict(c, UND) == (c["expect"]["ic00"], c["expect"]["payload"])


def test_counts() -> None:
    acc = [c for c in DET["cases"] if c["expect"]["result"] == "accept"]
    assert (len(DET["cases"]), len(acc)) == (61, 22)
    uacc = [c for c in UND["cases"] if c["expect"]["result"] == "accept"]
    assert (len(UND["cases"]), len(uacc)) == (2, 2)
    assert not set(DET_CASES) & set(UND_CASES)


def test_every_determined_case_cites_the_decision_wording() -> None:
    for c in DET["cases"]:
        assert c["derives_from"], c["id"]
        assert all(d.startswith("D-1") for d in c["derives_from"]), c["id"]
        assert not c["id"].startswith("undetermined"), c["id"]
        assert "tag" not in c, c["id"]


def test_every_undetermined_case_is_tagged_and_explained() -> None:
    for c in UND["cases"]:
        assert c["tag"] == "未規定", c["id"]
        assert c["undetermined_because"], c["id"]
        assert c["derives_from"], c["id"]


def test_the_requested_kinds_are_present() -> None:
    for needed in (
        "accept-rows-head", "accept-rows-middle", "accept-rows-tail",  # normal: head, middle, tail
        "accept-rows-boundary-end-equals-origin-length", "reject-rows-end-exceeds-origin-by-1",  # boundary
        "reject-rows-start-negative", "reject-rows-length-zero",
        "reject-rows-start-string", "reject-rows-length-string", "reject-rows-start-boolean",  # wrong types
        "accept-equivalence-prefix-rows-start-0", "accept-equivalence-rows-start-0",  # equivalence
        "accept-0.9.0-window-first-128", "reject-0.9.0-window-declaring-rows",  # reading 0.9.0
        "accept-windows-of-one-original-in-separate-spaces",  # space_id separation
        "reject-rows-parents-empty", "reject-rows-origin-trajectory-id-differs-from-stored", "reject-rows-source-not-stored",  # parent coherence
        "reject-pair-of-windows-of-different-lengths-equal-only",
    ):
        assert needed in DET_CASES, needed


def test_prefix_rows_and_rows_at_start_0_are_the_same_rows_with_the_same_verdict() -> None:
    a = DET_CASES["accept-equivalence-prefix-rows-start-0"]["envelope"]["payload"]
    b = DET_CASES["accept-equivalence-rows-start-0"]["envelope"]["payload"]
    assert a["points"] == b["points"] and a["window"]["content_sha256"] == b["window"]["content_sha256"]
    assert a["window"]["rule"] == "prefix_rows" and b["window"]["rule"] == "rows"
    assert {k: v for k, v in a["window"].items() if k != "rule"} == {k: v for k, v in b["window"].items() if k != "rule"}
    assert DET_CASES["accept-equivalence-prefix-rows-start-0"]["expect"] == DET_CASES["accept-equivalence-rows-start-0"]["expect"]


def test_a_0_9_0_window_is_read_by_its_own_version_and_never_as_0_10_0() -> None:
    c = DET_CASES["accept-0.9.0-window-first-128"]
    assert c["envelope"]["payload_schema"]["version"] == "0.9.0"
    assert PAYLOAD_SCHEMAS[("msr.trajectory-window", "0.9.0")] == "msr/archive/0.9.0/trajectory-window.schema.json"
    assert PAYLOAD_SCHEMAS[("msr.trajectory-window", "0.10.0")] == "msr/trajectory-window.schema.json"
    assert PAYLOAD_SCHEMAS[("msr.geometry-measurement", "0.9.0")] == "msr/archive/0.9.0/geometry-measurement.schema.json"
    assert PAYLOAD_SCHEMAS[("msr.geometry-measurement", "0.10.0")] == "msr/geometry-measurement.schema.json"


def test_the_pair_check_names_the_length_and_does_not_adopt_common_prefix() -> None:
    for cid in ("reject-pair-of-windows-of-different-lengths-equal-only", "reject-pair-of-windows-of-different-lengths-common-prefix"):
        assert DET_CASES[cid]["expect"]["payload"] == ["pair_window_length"]


def test_windows_of_different_positions_in_separate_spaces_are_accepted_together_and_sharing_one_is_rejected() -> None:
    assert DET_CASES["accept-windows-of-one-original-in-separate-spaces"]["expect"]["result"] == "accept"
    assert DET_CASES["reject-space-shared-by-two-positions"]["expect"]["payload"] == ["window_space_position"]


def test_d133_points_are_determined_and_the_undetermined_file_holds_only_what_d133_leaves_open() -> None:
    for cid in ("reject-token-index-beyond-origin-length", "reject-token-index-negative", "reject-rows-longer-than-origin", "accept-policy-name-free-form",
                "accept-prefix-rows-length-64", "reject-space-shared-by-two-positions", "accept-0.10.0-measurement-over-a-0.9.0-window"):
        assert any(d.startswith("D-133") for d in DET_CASES[cid]["derives_from"]), cid
    assert DET_CASES["reject-rows-longer-than-origin"]["expect"]["payload"] == ["window_range", "window_token_range"]
    assert set(UND_CASES) == {"undetermined-token-index-offset-from-row-numbers", "undetermined-pair-of-equal-length-windows-at-different-positions"}
    assert any(d.startswith("D-133 (6)") for d in UND_CASES["undetermined-pair-of-equal-length-windows-at-different-positions"]["derives_from"])
    assert "accept-pair-of-equal-length-windows-at-different-positions" not in DET_CASES


def test_vectors_regenerate_byte_identically(tmp_path: Path) -> None:
    import make_vectors_window as base
    import make_vectors_window_rows as gen

    saved = (gen.OUT, gen.OUT_UNDETERMINED)
    gen.OUT, gen.OUT_UNDETERMINED = tmp_path / "a.json", tmp_path / "b.json"
    try:
        base.BLOBS.clear()
        gen.main()
        assert gen.OUT.read_bytes() == saved[0].read_bytes()
        assert gen.OUT_UNDETERMINED.read_bytes() == saved[1].read_bytes()
    finally:
        gen.OUT, gen.OUT_UNDETERMINED = saved


@pytest.mark.parametrize("entry", LOCK["files"], ids=lambda e: e["path"])
def test_file_matches_the_ic02_0_10_0_lock(entry: dict[str, str]) -> None:
    assert hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]


def test_the_undetermined_vectors_are_not_locked() -> None:
    locked = {e["path"] for e in LOCK["files"]}
    assert "docs/architecture/contracts/msr/vectors/window-rows-undetermined.json" not in locked
    assert LOCK["not_locked"] == ["docs/architecture/contracts/msr/vectors/window-rows-undetermined.json"]


@pytest.mark.parametrize("rel", ["msr/trajectory-window.schema.json", "msr/geometry-measurement.schema.json"])
def test_new_schemas_are_valid_and_linted(rel: str) -> None:
    schema = load_schema(rel)
    Draft202012Validator.check_schema(schema)
    assert schema["$id"].endswith("/0.10.0")
    assert "0.10.0" in schema["title"]

    def walk(node: Any, path: str = "") -> Any:
        if isinstance(node, dict):
            yield path, node
            for k, v in node.items():
                yield from walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk(v, f"{path}/{i}")

    for path, node in walk(schema):
        t = node.get("type")
        types = [t] if isinstance(t, str) else list(t) if isinstance(t, list) else []
        if "integer" in types:
            assert ("minimum" in node or "exclusiveMinimum" in node) and ("maximum" in node or "exclusiveMaximum" in node), f"{path}: integer without bounds"
        if "array" in types:
            assert isinstance(node.get("x-sensos-ordered"), bool), f"{path}: missing x-sensos-ordered"


def test_the_window_schema_declares_start_and_length_as_bounded_integers() -> None:
    w = load_schema("msr/trajectory-window.schema.json")["properties"]["window"]["properties"]
    assert w["rule"]["enum"] == ["prefix_rows", "rows"]
    assert w["start"]["minimum"] == 0 and w["length"]["minimum"] == 1
    v = validator("msr/trajectory-window.schema.json")
    ok = DET_CASES["accept-rows-middle"]["envelope"]["payload"]
    assert list(v.iter_errors(ok)) == []


def test_rows_match_for_a_reader_holding_the_raw_rows() -> None:
    d = 3
    raw = struct.pack("<30f", *[float(i) for i in range(30)])  # 10 rows
    window = raw[4 * d * 4: 7 * d * 4]  # rows 4, 5, 6
    assert W.rows_match(window, raw, d, 4, 3)
    assert not W.rows_match(window, raw, d, 3, 3)
    assert not W.rows_match(window, raw, d, 8, 3)  # runs past the end
    assert W.rows_match(raw[: 2 * d * 4], raw, d, 0, 2) == W.prefix_matches.__call__(raw[: 2 * d * 4], raw[: 2 * d * 4], d)


def test_readme_documents_0_10_0_and_the_undetermined_list() -> None:
    text = (CONTRACTS_DIR / "msr/README.md").read_text(encoding="utf-8")
    for needle in ("IC-02 0.10.0", "D-132", "window_range", "pair_window_length", "未規定", "D-133", "archive/0.9.0/"):
        assert needle in text, needle
    assert (CONTRACTS_DIR / "IC-02/0.10.0/CHANGE.md").is_file()
