"""IC-00 1.1.0 (draft, D-107..D-110): rule selection, the producer registry, parent/child versions.

Reads only the 1.1.0 vectors (``IC-00/1.1.0/vectors/``); ``test_vectors.py`` keeps reading only
the 1.0.0 vectors. Nothing here changes what 1.0.0 accepts or rejects.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from contracts import check, ic00_v110, ic00_versions
from contracts.check import check_envelope
from contracts.schemas import ARCHIVED_PATHS, CONTRACTS_DIR, SCHEMA_PATHS, load_schema, registry, validator
from make_vectors_v110 import VECTORS_V110, generate

OLD_VECTORS = CONTRACTS_DIR / "common/vectors/check-envelope.json"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((VECTORS_V110 / name).read_text(encoding="utf-8"))
    return data


CHECK = _load("check-envelope.json")["cases"]
PARENTS = _load("parent-versions.json")["cases"]


def _codes(violations: list[check.Violation]) -> list[str]:
    return sorted({v.code for v in violations})


@pytest.mark.parametrize("case", CHECK, ids=[c["id"] for c in CHECK])
def test_rule_selection_and_registry_vectors(case: dict[str, Any]) -> None:
    codes = _codes(ic00_versions.check_envelope_versioned(case["envelope"], case["lookup"]))
    assert codes == case["expect"]["codes"]
    assert (not codes) == (case["expect"]["result"] == "accept")


@pytest.mark.parametrize("case", PARENTS, ids=[c["id"] for c in PARENTS])
def test_parent_versions_a_form(case: dict[str, Any]) -> None:
    assert _codes(ic00_versions.check_envelope_versioned(case["envelope"], case["lookup"])) == case["expect"]["a"]["codes"]


@pytest.mark.parametrize("case", PARENTS, ids=[c["id"] for c in PARENTS])
def test_parent_versions_b_form(case: dict[str, Any]) -> None:
    got = ic00_versions.check_envelope_with_parents(case["envelope"], case["parents"], case["ancestor_lookup"])
    assert _codes(got) == case["expect"]["b"]["codes"]


def test_the_four_version_pairs_are_independent_cases() -> None:
    pairs = {(c["parent_version"], c["child_version"]) for c in PARENTS if c["id"].startswith("parent-1.")}
    assert pairs == {("1.0.0", "1.0.0"), ("1.0.0", "1.1.0"), ("1.1.0", "1.1.0"), ("1.1.0", "1.0.0")}
    for c in PARENTS:
        if c["id"].startswith("parent-1.") and "built-on" not in c["id"]:
            assert c["expect"]["a"]["codes"] == [] and c["expect"]["b"]["codes"] == [], c["id"]


def test_a_and_b_differ_only_where_the_lookup_is_untrustworthy() -> None:
    differ = sorted(c["id"] for c in PARENTS if c["expect"]["a"] != c["expect"]["b"])
    assert differ == sorted(
        [
            "parent-1.0.0-child-1.1.0-built-on-parent-reread-as-1.1.0",
            "parent-1.1.0-child-1.0.0-built-on-parent-reread-as-1.0.0",
            "parent-unsupported-version-2.0.0",
            "grandparent-missing-from-ancestor-lookup",
            "parent-key-is-another-artifact",
        ]
    )


def test_parent_content_id_is_not_re_read_under_the_childs_version() -> None:
    from contracts import ids

    case = next(c for c in PARENTS if c["id"] == "parent-1.0.0-child-1.1.0")
    (parent,) = case["parents"].values()
    reread = json.loads(json.dumps(parent))
    reread["contract"]["version"] = "1.1.0"
    assert parent["contract"]["version"] == "1.0.0"
    assert ids.content_id(parent, {}) == parent["content_id"]
    assert ids.content_id(reread, {}) != parent["content_id"]


def test_1_0_0_check_envelope_is_unchanged_by_1_1_0() -> None:
    """The 1.0.0 entry point still treats a 1.1.0 envelope as a schema error (it knows one version)."""
    env = next(c for c in CHECK if c["id"] == "v110-nvs-kernel-observation")["envelope"]
    assert _codes(check_envelope(env, {})) == ["schema"]
    env = next(c for c in CHECK if c["id"] == "v110-sensos-connector-observation")["envelope"]
    assert _codes(check_envelope(env, {})) == ["schema"]


def test_versioned_entry_point_agrees_with_1_0_0_on_every_1_0_0_vector() -> None:
    """Same codes for every 1.0.0 vector whose contract.version is 1.0.0; the others differ only
    where the version is a string other than 1.0.0 (schema -> unsupported_contract_version)."""
    cases = json.loads(OLD_VECTORS.read_text(encoding="utf-8"))["cases"]
    same = other = 0
    for case in cases:
        env, lookup = case["envelope"], case["lookup"]
        old = _codes(check_envelope(env, lookup))
        new = _codes(ic00_versions.check_envelope_versioned(env, lookup))
        version = env.get("contract", {}).get("version") if isinstance(env.get("contract"), dict) else None
        if version == "1.0.0":
            assert new == old, case["id"]
            same += 1
        else:
            assert old == ["schema"], case["id"]
            assert new in (["schema"], ["unsupported_contract_version"]), case["id"]
            assert (new == ["unsupported_contract_version"]) == isinstance(version, str), case["id"]
            other += 1
    assert same + other == len(cases) and same >= 30


def test_producer_registry_is_1_0_0_plus_exactly_two_names() -> None:
    old, new = check.PRODUCER_KINDS, ic00_v110.PRODUCER_KINDS
    assert {k: v for k, v in new.items() if k in old} == old
    assert sorted(set(new) - set(old)) == ["sensos-connector", "sensos-inference"]
    assert new["sensos-connector"] == frozenset({"observation"})
    assert new["sensos-inference"] == frozenset({"observation"})
    assert ic00_v110.PRODUCER_PREFIXES == check.PRODUCER_PREFIXES


def test_supported_versions_are_exactly_1_0_0_and_1_1_0() -> None:
    assert sorted(ic00_versions.RULES) == ["1.0.0", "1.1.0"]


def test_1_1_0_schema_is_registered_nowhere_twice() -> None:
    """The 1.1.0 schema is read by path; its $id is not in SCHEMA_PATHS/ARCHIVED_PATHS, so registry()
    never holds the same $id twice."""
    schema = load_schema(ic00_v110.SCHEMA_PATH)
    assert schema["$id"] == "sensos:contracts/IC-00/artifact/1.1.0"
    listed = [load_schema(p)["$id"] for p in (*SCHEMA_PATHS, *ARCHIVED_PATHS)]
    assert len(listed) == len(set(listed))
    assert schema["$id"] not in listed
    assert schema["properties"]["contract"]["properties"]["version"] == {"const": "1.1.0"}
    assert list(validator(ic00_v110.SCHEMA_PATH).iter_errors(next(c for c in CHECK if c["id"] == "v110-nvs-kernel-observation")["envelope"])) == []
    assert registry() is not None


def test_1_1_0_vector_files_match_generator() -> None:
    for name, doc in generate().items():
        on_disk = json.loads((VECTORS_V110 / name).read_text(encoding="utf-8"))
        assert on_disk == json.loads(json.dumps(doc)), f"{name} is stale: rerun tools/contracts/make_vectors_v110.py"


def test_vector_counts_cover_the_decided_cases() -> None:
    ids_ = {c["id"] for c in CHECK}
    for needed in (
        "v100-sensos-connector-observation",
        "v110-sensos-connector-observation",
        "v110-sensos-connector-interpretation",
        "v100-nvs-kernel-observation",
        "v110-sensos-inference-observation",
        "v110-sensos-inference-interpretation",
        "v100-sensos-inference-observation",
        "unsupported-version-1.0.1",
    ):
        assert needed in ids_
    assert sum(1 for c in CHECK if c["expect"]["codes"] == ["unsupported_contract_version"]) >= 5
