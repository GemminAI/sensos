"""Backward compatibility of the 1.1.0 entry points with IC-00 1.0.0 (read-only use of the 1.0.0 vectors).

This is not the independent verification of 1.1.0 (D-108 (4), D-113); it checks only that the 1.1.0
entry points (``check_envelope_versioned``, ``check_envelope_with_parents``) leave 1.0.0 behaviour as it was.
Nothing here changes a 1.0.0 file; the 1.0.0 vectors are only read.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest
from contracts import ic00_versions, ids
from contracts.check import check_envelope
from contracts.jcs import jcs
from contracts.make_vectors import seal
from contracts.schemas import CONTRACTS_DIR
from make_vectors_v110 import VECTORS_V110

V100 = CONTRACTS_DIR / "common/vectors"
CHECK_100 = json.loads((V100 / "check-envelope.json").read_text(encoding="utf-8"))["cases"]
ENV_IDS = json.loads((V100 / "envelope-ids.json").read_text(encoding="utf-8"))
CHECK_110 = json.loads((VECTORS_V110 / "check-envelope.json").read_text(encoding="utf-8"))["cases"]
PARENTS_110 = json.loads((VECTORS_V110 / "parent-versions.json").read_text(encoding="utf-8"))["cases"]


def _codes(violations: list[Any]) -> list[str]:
    return sorted({v.code for v in violations})


def test_1_0_0_vector_counts_are_the_ones_checked() -> None:
    assert len(CHECK_100) == 37
    assert sum(c["expect"]["result"] == "accept" for c in CHECK_100) == 7
    assert sum(c["expect"]["result"] == "reject" for c in CHECK_100) == 30
    assert len(ENV_IDS["cases"]) == 17


@pytest.mark.parametrize("case", CHECK_100, ids=[c["id"] for c in CHECK_100])
def test_1_pass_every_1_0_0_check_vector_through_the_versioned_entry(case: dict[str, Any]) -> None:
    got = _codes(ic00_versions.check_envelope_versioned(case["envelope"], case["lookup"]))
    assert got == case["expect"]["codes"]  # (a) the vector's expectation
    assert (not got) == (case["expect"]["result"] == "accept")
    assert got == _codes(check_envelope(case["envelope"], case["lookup"]))  # (b) the 1.0.0 entry point
    assert "unsupported_contract_version" not in got  # 2.


@pytest.mark.parametrize("case", ENV_IDS["cases"], ids=[c["id"] for c in ENV_IDS["cases"]])
def test_3_1_0_0_ids_are_unchanged_through_the_1_1_0_paths(case: dict[str, Any]) -> None:
    env, lookup = case["envelope"], ENV_IDS["lookup"]
    assert env["contract"]["version"] == "1.0.0"
    assert ids.content_id(env, lookup) == case["expect"]["content_id"]
    assert ids.artifact_id(env, lookup) == case["expect"]["artifact_id"]
    assert hashlib.sha256(jcs(env)).hexdigest() == case["expect"]["envelope_jcs_sha256"]
    versioned = _codes(ic00_versions.check_envelope_versioned(env, lookup))
    assert versioned == _codes(check_envelope(env, lookup))
    assert "content_id_mismatch" not in versioned and "artifact_id_mismatch" not in versioned
    assert "unsupported_contract_version" not in versioned
    assert env["contract"]["version"] == "1.0.0"  # not re-read under 1.1.0


_NEW_NAMES = (("v110-sensos-connector-observation", "observation"), ("v110-sensos-inference-observation", "observation"),
              ("v110-sensos-connector-interpretation", "interpretation"), ("v110-sensos-inference-interpretation", "interpretation"))


@pytest.mark.parametrize(("cid", "_kind"), _NEW_NAMES, ids=[n for n, _ in _NEW_NAMES])
def test_4_1_1_0_producers_in_a_1_0_0_envelope_are_rejected_with_S4(cid: str, _kind: str) -> None:
    source = next(c for c in CHECK_110 if c["id"] == cid)["envelope"]
    env = copy.deepcopy(source)
    env["contract"]["version"] = "1.0.0"
    env = seal(env, {})
    assert env["contract"]["version"] == "1.0.0"
    assert _codes(ic00_versions.check_envelope_versioned(env, {})) == ["S4"]
    assert _codes(check_envelope(env, {})) == ["S4"]
    assert _codes(ic00_versions.check_envelope_with_parents(env, {}, {})) == ["S4"]


def test_5_1_0_0_parents_of_1_1_0_children_are_accepted_in_a_and_b() -> None:
    cases = [c for c in PARENTS_110 if c["parent_version"] == "1.0.0" and c["child_version"] == "1.1.0" and "built-on" not in c["id"]
             and c["expect"]["b"]["codes"] == [] and c["expect"]["a"]["codes"] == []]
    assert [c["id"] for c in cases] == ["parent-1.0.0-child-1.1.0"]
    for c in cases:
        assert _codes(ic00_versions.check_envelope_versioned(c["envelope"], c["lookup"])) == []
        assert _codes(ic00_versions.check_envelope_with_parents(c["envelope"], c["parents"], c["ancestor_lookup"])) == []
    assert len(PARENTS_110) == 14  # the range covered
