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
UNSPECIFIED = _load("parent-versions-unspecified.json")["cases"]


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


def test_d114_calibration_states_are_separate_in_1_1_0() -> None:
    """D-114 (1)(2): unknown / mismatch / lookup_incomplete, calibration_ref outside parents, null gives none."""
    by_id = {c["id"]: c for c in CHECK}
    expected = {
        "v110-calibration-null": [],
        "v110-calibration-ok-not-in-parents": [],
        "v110-calibration-unknown-not-in-parents": ["calibration_unknown"],
        "v110-calibration-mismatch": ["calibration_mismatch"],
        "v110-calibration-lookup-incomplete": ["lookup_incomplete"],
        **{f"v110-calibration-lookup-content-id-{k}": ["lookup_incomplete"] for k in ("null", "int", "bool", "list", "dict")},  # D-115
        **{f"v100-calibration-lookup-content-id-{k}": ["calibration_mismatch"] for k in ("null", "int", "bool", "list", "dict")},
        # D-116 (1): a malformed string is incomplete in 1.1.0 (mismatch in 1.0.0)
        "v110-calibration-lookup-content-id-bad-format": ["lookup_incomplete"],
        "v100-calibration-lookup-content-id-bad-format": ["calibration_mismatch"],
        # 1.0.0 is unchanged: an entry without content_id is a mismatch there
        "v100-calibration-null": [],
        "v100-calibration-ok-not-in-parents": [],
        "v100-calibration-unknown-not-in-parents": ["calibration_unknown"],
        "v100-calibration-mismatch": ["calibration_mismatch"],
        "v100-calibration-lookup-incomplete": ["calibration_mismatch"],
    }
    for cid, codes in expected.items():
        assert by_id[cid]["expect"]["codes"] == codes, cid
        assert "parent_unknown" not in by_id[cid]["expect"]["codes"]
        assert not by_id[cid]["envelope"]["parents"]


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
            "parent-key-is-another-artifact",
            "child-S4-with-invalid-parent",
            "unreferenced-invalid-parent-entry",
        ]
    )


def test_b_form_follows_d111_d112_order() -> None:
    """D-111 (2), D-112 (2)(3)(4): a code of the child's step 1 or of step 2 (the parents) is returned alone."""
    by_id = {c["id"]: c for c in PARENTS}
    for cid, codes in (
        ("parent-unsupported-version-2.0.0", ["parent_invalid"]),
        ("parent-key-is-another-artifact", ["parent_key_mismatch", "parent_unknown"]),  # D-111 (4)
        ("child-unsupported-version-with-invalid-parent", ["unsupported_contract_version"]),
        ("child-schema-error-with-invalid-parent", ["schema"]),
        ("child-S4-with-invalid-parent", ["parent_invalid"]),
        ("child-S4-with-valid-parent", ["S4"]),
        ("unreferenced-invalid-parent-entry", ["parent_invalid"]),
    ):
        assert by_id[cid]["expect"]["b"]["codes"] == codes, cid
    for c in PARENTS:
        b = set(c["expect"]["b"]["codes"])
        step2 = {"parent_invalid", "parent_key_mismatch", "parent_unknown"}
        assert not (b & step2 and b - step2), c["id"]  # no step 3 code beside a step 2 code


def test_d113_the_grandparent_case_is_outside_the_frozen_vectors() -> None:
    """D-113: moved, expectations unchanged; 14 frozen cases, 1 unspecified."""
    assert len(PARENTS) == 14 and len(UNSPECIFIED) == 1
    (case,) = UNSPECIFIED
    assert case["id"] == "grandparent-missing-from-ancestor-lookup"
    assert case["expect"] == {"a": {"codes": []}, "b": {"codes": ["parent_invalid", "parent_unknown"]}}
    assert case["id"] not in {c["id"] for c in PARENTS}
    assert _codes(ic00_versions.check_envelope_versioned(case["envelope"], case["lookup"])) == []


def test_unspecified_b_form_cases_are_outside_the_frozen_vectors() -> None:
    doc = _load("parent-versions-unspecified.json")
    assert doc["status"].startswith("not frozen")
    assert isinstance(doc["cases"], list)
    assert not {c["id"] for c in doc["cases"]} & {c["id"] for c in PARENTS}
    for c in doc["cases"]:
        got = ic00_versions.check_envelope_with_parents(c["envelope"], c["parents"], c["ancestor_lookup"])
        assert _codes(got) == c["expect"]["b"]["codes"], c["id"]


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


# ---- D-116 (6): which checks ran and which did not ---------------------------------------------------------
# Observed from outside: the lookup handed to the checker records every read of an entry and of its fields, and
# a tampered input makes an id recomputation visible in the codes. Nothing of the implementation is inspected.

from contracts.make_vectors import _env, _stored, seal  # noqa: E402
from make_vectors_v110 import _OBS0, _SES, _root, _with_cal  # noqa: E402


class _Entry(dict):  # type: ignore[type-arg]
    def __init__(self, data: dict[str, Any], log: list[tuple[str, str]], name: str) -> None:
        super().__init__(data)
        self._log, self._name = log, name

    def get(self, key: str, default: Any = None) -> Any:
        self._log.append((self._name, key))
        return super().get(key, default)

    def __getitem__(self, key: str) -> Any:
        self._log.append((self._name, key))
        return super().__getitem__(key)


class _Lookup(dict):  # type: ignore[type-arg]
    """Records which entries were fetched by value (`fetch`) and which only probed (`probe`)."""

    def __init__(self, data: dict[str, dict[str, Any]], names: dict[str, str]) -> None:
        self.log: list[tuple[str, str]] = []
        super().__init__({k: _Entry(v, self.log, names[k]) for k, v in data.items()})
        self._names = names

    def __contains__(self, key: object) -> bool:
        self.log.append((self._names.get(str(key), "?"), "<probe>"))
        return super().__contains__(key)

    def get(self, key: str, default: Any = None) -> Any:
        self.log.append((self._names.get(key, "?"), "<get>"))
        return super().get(key, default)

    def __getitem__(self, key: str) -> Any:
        self.log.append((self._names.get(key, "?"), "<fetch>"))
        return super().__getitem__(key)

    def fields_read(self, name: str) -> set[str]:
        return {f for n, f in self.log if n == name and not f.startswith("<")}

    def fetched(self, name: str) -> bool:
        return (name, "<fetch>") in self.log


def _cal_world(version: str = "1.1.0") -> dict[str, Any]:
    cal = _root("meaning-space-runtime", "interpretation", version, seq=1, payload={"calibration": 1})
    ref = {"artifact_id": cal["artifact_id"], "content_id": cal["content_id"]}
    return {"cal": cal, "ref": ref, "child": _with_cal(version, ref), "stored": _stored(cal), "version": version}


def _run_cal(env: Any, entry: dict[str, Any] | None, w: dict[str, Any]) -> tuple[list[str], _Lookup]:
    data = {} if entry is None else {w["cal"]["artifact_id"]: entry}
    lookup = _Lookup(data, {w["cal"]["artifact_id"]: "cal"})
    return _codes(ic00_versions.check_envelope_versioned(env, lookup)), lookup


def _tampered(env: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(env))
    out["payload"] = {"n": 999}
    return out


def test_d116_calibration_unknown_skips_the_s5_comparison_and_runs_the_id_recomputation() -> None:
    w = _cal_world()
    codes, lookup = _run_cal(w["child"], None, w)
    assert codes == ["calibration_unknown"]
    assert not lookup.fetched("cal") and not lookup.fields_read("cal")  # no entry: nothing of it is read by S5
    codes, _ = _run_cal(_tampered(w["child"]), None, w)  # the id recomputation runs without the calibration entry
    assert codes == ["artifact_id_mismatch", "calibration_unknown", "content_id_mismatch"]


@pytest.mark.parametrize("bad", [None, 5, True, ["x"], {"a": 1}, "not-a-content-id", "<absent>"], ids=["null", "int", "bool", "list", "dict", "bad-format", "absent"])
def test_d116_lookup_incomplete_from_content_id_runs_s5_and_the_id_recomputation(bad: Any) -> None:
    w = _cal_world()
    entry = dict(w["stored"])
    if bad == "<absent>":
        entry.pop("content_id")
    else:
        entry["content_id"] = bad
    codes, lookup = _run_cal(w["child"], entry, w)
    assert codes == ["lookup_incomplete"]
    assert {"content_id", "seq"} <= lookup.fields_read("cal")  # the content_id check and the S5 comparison both read the entry
    late = dict(entry, seq=5)  # S5 ran: a calibration seq not before the child's is reported
    assert _run_cal(w["child"], late, w)[0] == ["S5", "lookup_incomplete"]
    assert _run_cal(_tampered(w["child"]), entry, w)[0] == ["artifact_id_mismatch", "content_id_mismatch", "lookup_incomplete"]  # ids ran
    # 1.0.0: the same stored content_id is a mismatch there, with the same checks run
    w0 = _cal_world("1.0.0")
    e0 = dict(w0["stored"])
    if bad == "<absent>":
        e0.pop("content_id")
    else:
        e0["content_id"] = bad
    assert _run_cal(w0["child"], e0, w0)[0] == ["calibration_mismatch"]


@pytest.mark.parametrize("seq", ["1", None, True, "<absent>"], ids=["str", "null", "bool", "absent"])
def test_d116_lookup_incomplete_from_seq_does_not_stop_the_other_checks(seq: Any) -> None:
    w = _cal_world()
    entry = dict(w["stored"])
    if seq == "<absent>":
        entry.pop("seq")
    else:
        entry["seq"] = seq
    codes, lookup = _run_cal(w["child"], entry, w)
    assert codes == ["lookup_incomplete"] and {"content_id", "seq"} <= lookup.fields_read("cal")
    wrong = dict(entry, content_id="cnt:" + "9" * 64)  # the content_id comparison ran too
    assert _run_cal(w["child"], wrong, w)[0] == ["calibration_mismatch", "lookup_incomplete"]
    assert _run_cal(_tampered(w["child"]), entry, w)[0] == ["artifact_id_mismatch", "content_id_mismatch", "lookup_incomplete"]


def test_d116_calibration_entry_observation_id_is_never_read() -> None:
    w = _cal_world()
    for obs in ("<absent>", None, 5):
        entry = dict(w["stored"])
        if obs == "<absent>":
            entry.pop("observation_id")
        else:
            entry["observation_id"] = obs
        codes, lookup = _run_cal(w["child"], entry, w)
        assert codes == [] and "observation_id" not in lookup.fields_read("cal")


def _s8_world(version: str = "1.1.0") -> dict[str, Any]:
    parent = _root("nvs-kernel", "observation", version, seq=1)  # observation_id OBS0

    def child(obs: str | None) -> dict[str, Any]:
        env = _env(name="meaning-space-runtime", kind="interpretation", payload={"n": 2}, seq=2, session=_SES, obs=obs,
                   parents=[{"role": "trajectory", "ordered": False, "artifact_ids": [parent["artifact_id"]]}])
        env["contract"]["version"] = version
        return seal(env, {parent["artifact_id"]: _stored(parent)})

    return {"parent": parent, "child": child}


@pytest.mark.parametrize("version", ["1.1.0", "1.0.0"])
@pytest.mark.parametrize(
    ("parent_obs", "child_obs", "codes"),
    [
        ("<absent>", "null", []), ("null", "null", []), ("<absent>", "OBS0", ["S8"]), ("null", "OBS0", ["S8"]),  # D-116 (2): all parents null or missing
        ("OBS0", "OBS0", []), ("OBS0", "null", ["S8"]),  # one non-null kind
        (5, "OBS0", ["S8"]), (5, "null", ["S8"]), ("", "OBS0", ["S8"]), ("", "null", ["S8"]),  # int and "" are one non-null kind, unchecked
    ],
)
def test_d116_s8_contract_table(version: str, parent_obs: Any, child_obs: str, codes: list[str]) -> None:
    w = _s8_world(version)
    entry = dict(_stored(w["parent"]))
    if parent_obs == "<absent>":
        entry.pop("observation_id")
    else:
        entry["observation_id"] = {"null": None, "OBS0": _OBS0}.get(parent_obs, parent_obs) if isinstance(parent_obs, str) else parent_obs
    child = w["child"]({"null": None, "OBS0": _OBS0}[child_obs])
    got = _codes(ic00_versions.check_envelope_versioned(child, {w["parent"]["artifact_id"]: entry}))
    assert got == codes  # no lookup_incomplete for a missing observation_id
    ids_ran = _codes(ic00_versions.check_envelope_versioned(_tampered(child), {w["parent"]["artifact_id"]: entry}))
    assert {"content_id_mismatch", "artifact_id_mismatch"} <= set(ids_ran)  # the id recomputation does not depend on observation_id


def test_d116_b_form_does_not_run_step_3_when_step_2_reports() -> None:
    w = _s8_world()
    bad = _root("nvs-kernel", "observation", "1.1.0", seq=1)
    bad["contract"]["version"] = "2.0.0"
    bad = seal(bad, {})
    env = _env(name="meaning-space-runtime", kind="interpretation", payload={"n": 2}, seq=2, session=_SES, obs="obs:" + "7" * 64,
               calibration_ref={"artifact_id": "art:" + "1" * 64, "content_id": "cnt:" + "2" * 64},
               parents=[{"role": "trajectory", "ordered": False, "artifact_ids": [bad["artifact_id"]]}])
    env["contract"]["version"] = "1.1.0"
    child = seal(env, {bad["artifact_id"]: _stored(bad)})
    child["content_id"] = "cnt:" + "f" * 64  # step 3 would report: id mismatch, S8, calibration_unknown
    got = _codes(ic00_versions.check_envelope_with_parents(child, {bad["artifact_id"]: bad}, {}))
    assert got == ["parent_invalid"]
    # with a valid parent the same child reaches step 3 (the codes step 3 gives)
    good = w["parent"]
    env2 = json.loads(json.dumps(child))
    env2["parents"][0]["artifact_ids"] = [good["artifact_id"]]
    env2["content_id"] = "cnt:" + "f" * 64
    reached = _codes(ic00_versions.check_envelope_with_parents(env2, {good["artifact_id"]: good}, {}))
    assert {"calibration_unknown", "content_id_mismatch", "S8"} <= set(reached)


# ---- D-117: S8 of 1.1.0 counts kinds by equality; a list or a dict does not raise ----

def _obs1() -> str:
    from contracts import ids

    return ids.observation_id(_SES, 1)


def _s8_multi(parent_obs: list[Any], child_obs: str | None, *, child_seq: int = 2, parent_seq: int = 1, producer: str = "meaning-space-runtime") -> tuple[dict[str, Any], dict[str, Any]]:
    parents = [_root("nvs-kernel", "observation", "1.1.0", seq=parent_seq, payload={"n": 1, "parent": i}) for i in range(len(parent_obs))]
    lookup = {}
    for parent, value in zip(parents, parent_obs, strict=True):
        entry = dict(_stored(parent))
        if value == "<absent>":
            entry.pop("observation_id")
        else:
            entry["observation_id"] = value
        lookup[parent["artifact_id"]] = entry
    env = _env(name=producer, kind="interpretation", payload={"n": 2}, seq=child_seq, session=_SES, obs=child_obs,
               parents=[{"role": "trajectory", "ordered": False, "artifact_ids": sorted(p["artifact_id"] for p in parents)}])
    env["contract"]["version"] = "1.1.0"
    return seal(env, {p["artifact_id"]: _stored(p) for p in parents}), lookup


def _run_s8(parent_obs: list[Any], child_obs: str | None, **kw: Any) -> list[str]:
    child, lookup = _s8_multi(parent_obs, child_obs, **kw)
    return _codes(ic00_versions.check_envelope_versioned(child, lookup))


@pytest.mark.parametrize("value", [[], ["OBS0"], {}, {"a": 1}], ids=["list-empty", "list-OBS0", "dict-empty", "dict-a1"])
@pytest.mark.parametrize("child_obs", [_OBS0, None], ids=["child-OBS0", "child-null"])
def test_d117_list_and_dict_in_a_parent_entry_do_not_raise_and_are_one_non_null_kind(value: Any, child_obs: str | None) -> None:
    assert _run_s8([value], child_obs) == ["S8"]
    # the other checks still return their codes: S4 (producer), S5 (seq), and the id recomputation
    assert _run_s8([value], child_obs, producer="mystery-tool") == ["S4", "S8"]
    assert _run_s8([value], child_obs, parent_seq=5) == ["S5", "S8"]
    child, lookup = _s8_multi([value], child_obs)
    assert {"content_id_mismatch", "artifact_id_mismatch", "S8"} <= set(_codes(ic00_versions.check_envelope_versioned(_tampered(child), lookup)))


@pytest.mark.parametrize(
    ("pair", "child_obs", "codes"),
    [
        (["OBS0", "<absent>"], "OBS0", []), (["OBS0", "<absent>"], None, ["S8"]),
        (["OBS0", None], "OBS0", []), (["OBS0", None], None, ["S8"]),
        (["OBS0", "OBS1"], "OBS0", ["S8"]), (["OBS0", "OBS1"], None, []),
        (["<absent>", None], "OBS0", ["S8"]), (["<absent>", None], None, []),
        (["OBS0", 5], "OBS0", ["S8"]), (["OBS0", 5], None, []),
        (["OBS0", "OBS0"], "OBS0", []), (["OBS0", "OBS0"], None, ["S8"]),
        (["OBS0", [1]], "OBS0", ["S8"]), (["OBS0", {"a": 1}], None, []),  # a list or a dict among several parents
        ([[1], [1]], None, ["S8"]), ([[1], [2]], None, []),  # equal lists are one kind, different lists are two
    ],
)
def test_d117_s8_over_several_parents_is_independent_of_their_order(pair: list[Any], child_obs: str | None, codes: list[str]) -> None:
    real = {"OBS0": _OBS0, "OBS1": _obs1()}
    resolve = lambda v: real.get(v, v) if isinstance(v, str) and v in real else v  # noqa: E731
    child_value = _OBS0 if child_obs == "OBS0" else child_obs
    first = _run_s8([resolve(v) for v in pair], child_value)
    swapped = _run_s8([resolve(v) for v in reversed(pair)], child_value)
    assert first == codes == swapped


def test_d117_one_and_true_are_one_kind_as_in_1_0_0() -> None:
    """The kinds are counted with ==, so 1 and True are one kind, as in the set 1.0.0's check._s8 builds."""
    assert _run_s8([1, True], None) == ["S8"]   # one kind: a null child is S8
    assert _run_s8([1, True], _OBS0) == ["S8"]  # one non-null kind that is not the child's
    assert _run_s8([1, 2], None) == []          # two kinds
    for version_run in (_run_s8,):
        assert version_run([True], None) == ["S8"] and version_run([False], None) == ["S8"]  # bool: one non-null kind (D-117)


def test_d117_1_1_0_has_its_own_s8_and_1_0_0_check_s8_is_unchanged() -> None:
    assert ic00_v110._s8 is not check._s8
    # 1.0.0 (frozen, not changed): a list or a dict among the parents' observation_id raises TypeError
    parent = _root("nvs-kernel", "observation", "1.0.0", seq=1)
    entry = dict(_stored(parent))
    entry["observation_id"] = ["OBS0"]
    env = _env(name="meaning-space-runtime", kind="interpretation", payload={"n": 2}, seq=2, session=_SES, obs=_OBS0,
               parents=[{"role": "trajectory", "ordered": False, "artifact_ids": [parent["artifact_id"]]}])
    child = seal(env, {parent["artifact_id"]: _stored(parent)})
    with pytest.raises(TypeError):
        check_envelope(child, {parent["artifact_id"]: entry})


def test_d117_vectors_for_list_and_dict_are_1_1_0_only() -> None:
    ids_ = [c["id"] for c in CHECK if "-s8-" in c["id"]]
    assert len(ids_) == 20 and all(i.startswith("v110-") for i in ids_)
