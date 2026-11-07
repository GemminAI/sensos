"""Generate the IC-00 1.1.0 vectors (docs/architecture/contracts/IC-00/1.1.0/vectors/).

Run:  python tools/contracts/make_vectors_v110.py  (from the repository root)

Separate from ``make_vectors.py`` (which owns the 1.0.0 vectors and is never run for
1.1.0). This module only imports its envelope builders (``_env``, ``seal``,
``_stored``); it does not call ``make_vectors.generate()`` or ``main()``.

The expected codes below are written by hand from the rules (D-108 (6), D-110), not
taken from the implementation under test.

Files:
  check-envelope.json    rule selection and the producer registry. Input:
                         ``check_envelope_versioned(envelope, lookup)`` (the A form).
  parent-versions.json   parent/child contract versions (D-110 (2)(3)). Each case has the A
                         input (``lookup``) and the B input (``parents``, ``ancestor_lookup``)
                         and the expected codes for both.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts import ids  # noqa: E402
from contracts.make_vectors import _env, _stored, seal  # noqa: E402

VECTORS_V110 = Path(__file__).resolve().parents[2] / "docs/architecture/contracts/IC-00/1.1.0/vectors"

_SES = ids.session_id_experiment("sha256:" + "c" * 64, "item-001", "baseline", 0, 7)
_OBS0 = ids.observation_id(_SES, 0)


def _root(name: str, kind: str, version: str, seq: int = 1, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    env = _env(
        name=name,
        kind=kind,
        payload=payload or {"n": seq},
        seq=seq,
        session=_SES,
        obs=_OBS0 if kind == "observation" else None,
    )
    env["contract"]["version"] = version
    return seal(env, {})


def _child(
    name: str,
    kind: str,
    version: str,
    parent_ids: list[str],
    lookup: dict[str, dict[str, Any]],
    seq: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    env = _env(
        name=name,
        kind=kind,
        payload=payload or {"n": seq},
        seq=seq,
        session=_SES,
        obs=_OBS0,
        parents=[{"role": "trajectory", "ordered": False, "artifact_ids": sorted(parent_ids)}],
    )
    env["contract"]["version"] = version
    return seal(env, lookup)


def check_cases() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def case(cid: str, env: Any, codes: list[str], lookup: dict[str, Any] | None = None) -> None:
        cases.append(
            {
                "id": cid,
                "envelope": env,
                "lookup": lookup or {},
                "expect": {"codes": codes, "result": "accept" if not codes else "reject"},
            }
        )

    # producer registry per version (D-108 (1)(2)(6))
    case("v100-sensos-connector-observation", _root("sensos-connector", "observation", "1.0.0"), ["S4"])
    case("v110-sensos-connector-observation", _root("sensos-connector", "observation", "1.1.0"), [])
    case("v110-sensos-connector-interpretation", _root("sensos-connector", "interpretation", "1.1.0"), ["S4"])
    case("v110-sensos-connector-selection", _root("sensos-connector", "selection", "1.1.0"), ["S4"])
    case("v110-sensos-inference-observation", _root("sensos-inference", "observation", "1.1.0"), [])
    case("v110-sensos-inference-interpretation", _root("sensos-inference", "interpretation", "1.1.0"), ["S4"])
    case("v100-sensos-inference-observation", _root("sensos-inference", "observation", "1.0.0"), ["S4"])
    # producers allowed in 1.0.0 are accepted in both versions
    case("v100-nvs-kernel-observation", _root("nvs-kernel", "observation", "1.0.0"), [])
    case("v110-nvs-kernel-observation", _root("nvs-kernel", "observation", "1.1.0"), [])
    case("v100-hext-evidence", _root("hext", "evidence", "1.0.0"), [])
    case("v110-hext-evidence", _root("hext", "evidence", "1.1.0"), [])
    case("v100-sensos-ux-selection", _root("sensos-ux", "selection", "1.0.0"), [])
    case("v110-sensos-ux-selection", _root("sensos-ux", "selection", "1.1.0"), [])
    case("v110-adapter-prefix-interpretation", _root("adapter:carry-evidence", "interpretation", "1.1.0"), [])
    case("v110-capability-prefix-interpretation", _root("capability:fs-read", "interpretation", "1.1.0"), [])
    case("v110-unknown-producer", _root("mystery-tool", "observation", "1.1.0"), ["S4"])
    case("v100-unknown-producer", _root("mystery-tool", "observation", "1.0.0"), ["S4"])

    # unsupported versions: a dedicated code, not `schema`, and never a newer rule applied (D-110 (1))
    for version in ("1.0.1", "1.2.0", "2.0.0", "0.6.2", "1.1", "1.1.0-rc1", ""):
        env = _root("nvs-kernel", "observation", "1.0.0")
        env["contract"]["version"] = version
        case(f"unsupported-version-{version or 'empty'}", env, ["unsupported_contract_version"])
    env = _root("sensos-connector", "observation", "1.1.0")
    env["contract"]["version"] = "1.2.0"
    case("unsupported-version-1.2.0-would-pass-110-rules", env, ["unsupported_contract_version"])

    # a version cannot be read: structure error, no rule selected
    base = _root("nvs-kernel", "observation", "1.0.0")
    no_contract = {k: v for k, v in base.items() if k != "contract"}
    case("no-contract", no_contract, ["schema"])
    case("contract-null", {**base, "contract": None}, ["schema"])
    case("contract-string", {**base, "contract": "IC-00 1.1.0"}, ["schema"])
    case("contract-list", {**base, "contract": ["IC-00", "1.1.0"]}, ["schema"])
    case("contract-without-version", {**base, "contract": {"id": "IC-00"}}, ["schema"])
    case("contract-version-number", {**base, "contract": {"id": "IC-00", "version": 110}}, ["schema"])
    case("contract-version-null", {**base, "contract": {"id": "IC-00", "version": None}}, ["schema"])
    case("envelope-is-a-list", [], ["schema"])
    case("envelope-is-null", None, ["schema"])
    # a readable supported version but another contract id: the version's schema decides
    wrong_id = _root("nvs-kernel", "observation", "1.1.0")
    wrong_id["contract"]["id"] = "IC-99"
    case("v110-wrong-contract-id", wrong_id, ["schema"])

    # D-114: calibration_ref only (no parents, so no parent_unknown). The calibration artifact is in the lookup
    # only; calibration_ref need not be in parents (IC-00 envelope level; S20 is IC-02's rule).
    def with_cal(version: str, ref: dict[str, str] | None) -> dict[str, Any]:
        env = _env(name="meaning-space-runtime", kind="interpretation", payload={"n": 2}, seq=2, session=_SES, obs=None, calibration_ref=ref)
        env["contract"]["version"] = version
        return seal(env, {})

    for version in ("1.1.0", "1.0.0"):
        cal = _root("meaning-space-runtime", "interpretation", version, seq=1, payload={"calibration": 1})
        cal_lookup = {cal["artifact_id"]: _stored(cal)}
        ref = {"artifact_id": cal["artifact_id"], "content_id": cal["content_id"]}
        tag = "v110" if version == "1.1.0" else "v100"
        case(f"{tag}-calibration-null", with_cal(version, None), [])
        case(f"{tag}-calibration-ok-not-in-parents", with_cal(version, ref), [], cal_lookup)
        case(f"{tag}-calibration-unknown-not-in-parents", with_cal(version, ref), ["calibration_unknown"])
        wrong = {**ref, "content_id": "cnt:" + "9" * 64}
        case(f"{tag}-calibration-mismatch", with_cal(version, wrong), ["calibration_mismatch"], cal_lookup)
        incomplete = {cal["artifact_id"]: {k: v for k, v in _stored(cal).items() if k != "content_id"}}
        # D-114 (1): 1.1.0 separates "entry without content_id" from a mismatch; 1.0.0 reports a mismatch
        case(f"{tag}-calibration-lookup-incomplete", with_cal(version, ref), ["lookup_incomplete"] if version == "1.1.0" else ["calibration_mismatch"], incomplete)
    return {"cases": cases}


def _stored_map(*envs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["artifact_id"]: _stored(e) for e in envs}


def parent_cases() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(
        cid: str,
        parent_version: str,
        child_version: str,
        child: dict[str, Any],
        lookup: dict[str, dict[str, Any]],
        parents: dict[str, dict[str, Any]],
        ancestor_lookup: dict[str, dict[str, Any]],
        a: list[str],
        b: list[str],
    ) -> None:
        cases.append(
            {
                "id": cid,
                "parent_version": parent_version,
                "child_version": child_version,
                "envelope": child,
                "lookup": lookup,
                "parents": parents,
                "ancestor_lookup": ancestor_lookup,
                "expect": {"a": {"codes": a}, "b": {"codes": b}},
            }
        )

    # the four combinations (parent -> child), D-110 (3); the 1.1.0 parent is a sensos-inference
    # observation, which only the 1.1.0 rule allows: the child's version must not matter for it.
    for pv, cv in (("1.0.0", "1.0.0"), ("1.0.0", "1.1.0"), ("1.1.0", "1.1.0"), ("1.1.0", "1.0.0")):
        parent = _root("sensos-inference" if pv == "1.1.0" else "nvs-kernel", "observation", pv)
        lookup = _stored_map(parent)
        child = _child("meaning-space-runtime", "interpretation", cv, [parent["artifact_id"]], lookup, seq=2)
        add(f"parent-{pv}-child-{cv}", pv, cv, child, lookup, {parent["artifact_id"]: parent}, {}, [], [])

    # the child was built on the parent's content_id re-read under the other version: A trusts the
    # lookup and accepts; B derives the parent's content_id from the parent's own contract and rejects
    for pv, cv, other in (("1.0.0", "1.1.0", "1.1.0"), ("1.1.0", "1.0.0", "1.0.0")):
        parent = _root("nvs-kernel", "observation", pv)
        reread = copy.deepcopy(parent)
        reread["contract"]["version"] = other
        wrong = {parent["artifact_id"]: {**_stored(parent), "content_id": ids.content_id(reread, {})}}
        assert wrong[parent["artifact_id"]]["content_id"] != parent["content_id"]
        child = _child("meaning-space-runtime", "interpretation", cv, [parent["artifact_id"]], wrong, seq=2)
        add(
            f"parent-{pv}-child-{cv}-built-on-parent-reread-as-{other}",
            pv,
            cv,
            child,
            wrong,
            {parent["artifact_id"]: parent},
            {},
            [],
            ["artifact_id_mismatch", "content_id_mismatch"],
        )

    # a parent of an unsupported version: A cannot see it; B rejects it (and the child loses it)
    parent = _root("nvs-kernel", "observation", "1.0.0")
    parent["contract"]["version"] = "2.0.0"
    parent = seal(parent, {})
    lookup = _stored_map(parent)
    child = _child("meaning-space-runtime", "interpretation", "1.1.0", [parent["artifact_id"]], lookup, seq=2)
    add(
        "parent-unsupported-version-2.0.0",
        "2.0.0",
        "1.1.0",
        child,
        lookup,
        {parent["artifact_id"]: parent},
        {},
        [],
        ["parent_invalid"],
    )

    # B: the parents' own parents (ancestor_lookup), a 1.0.0 root -> 1.1.0 parent -> 1.0.0 child
    grand = _root("nvs-kernel", "observation", "1.0.0")
    g_lookup = _stored_map(grand)
    mid = _child("nvs-runtime", "interpretation", "1.1.0", [grand["artifact_id"]], g_lookup, seq=2)
    lookup = _stored_map(mid)
    child = _child("meaning-space-runtime", "interpretation", "1.0.0", [mid["artifact_id"]], lookup, seq=3)
    add("grandparent-1.0.0-parent-1.1.0-child-1.0.0", "1.1.0", "1.0.0", child, lookup, {mid["artifact_id"]: mid}, g_lookup, [], [])
    add(
        "grandparent-missing-from-ancestor-lookup",
        "1.1.0",
        "1.0.0",
        child,
        lookup,
        {mid["artifact_id"]: mid},
        {},
        [],
        ["parent_invalid", "parent_unknown"],
    )

    # B: the key is not the parent's artifact_id
    parent = _root("nvs-kernel", "observation", "1.0.0")
    other = _root("nvs-kernel", "observation", "1.0.0", seq=5, payload={"n": 99})
    lookup = _stored_map(parent)
    child = _child("meaning-space-runtime", "interpretation", "1.1.0", [parent["artifact_id"]], lookup, seq=6)
    add(
        "parent-key-is-another-artifact",
        "1.0.0",
        "1.1.0",
        child,
        lookup,
        {parent["artifact_id"]: other},
        {},
        [],
        ["parent_key_mismatch", "parent_unknown"],
    )

    # D-112 (2)(3)(4). A trusts the lookup, so the parent is invisible to it.
    bad_parent = _root("nvs-kernel", "observation", "1.0.0")
    bad_parent["contract"]["version"] = "2.0.0"
    bad_parent = seal(bad_parent, {})
    bad_lookup = _stored_map(bad_parent)
    bad_map = {bad_parent["artifact_id"]: bad_parent}

    # (2) a code in step 1 (version, schema) of the child is returned alone; the parents are not looked at
    child = _child("meaning-space-runtime", "interpretation", "1.1.0", [bad_parent["artifact_id"]], bad_lookup, seq=2)
    unsupported_child = copy.deepcopy(child)
    unsupported_child["contract"]["version"] = "3.0.0"
    add("child-unsupported-version-with-invalid-parent", "2.0.0", "3.0.0", unsupported_child, bad_lookup, bad_map, {},
        ["unsupported_contract_version"], ["unsupported_contract_version"])
    schema_child = copy.deepcopy(child)
    schema_child["unknown_field"] = 1
    add("child-schema-error-with-invalid-parent", "2.0.0", "1.1.0", schema_child, bad_lookup, bad_map, {},
        ["schema"], ["schema"])

    # (3) S4 belongs to step 3: with an invalid parent it is not reported, with valid parents it is
    s4_child = _child("hext", "interpretation", "1.1.0", [bad_parent["artifact_id"]], bad_lookup, seq=2)
    add("child-S4-with-invalid-parent", "2.0.0", "1.1.0", s4_child, bad_lookup, bad_map, {}, ["S4"], ["parent_invalid"])
    good = _root("nvs-kernel", "observation", "1.0.0")
    good_lookup = _stored_map(good)
    s4_child = _child("hext", "interpretation", "1.1.0", [good["artifact_id"]], good_lookup, seq=2)
    add("child-S4-with-valid-parent", "1.0.0", "1.1.0", s4_child, good_lookup, {good["artifact_id"]: good}, {}, ["S4"], ["S4"])

    # (4) an entry of parent_envelopes the child does not refer to is checked too
    child = _child("meaning-space-runtime", "interpretation", "1.1.0", [good["artifact_id"]], good_lookup, seq=2)
    add("unreferenced-invalid-parent-entry", "1.0.0", "1.1.0", child, good_lookup,
        {good["artifact_id"]: good, **bad_map}, {}, [], ["parent_invalid"])
    return {"cases": cases}


# D-113: excluded from the freeze (D-111 (4) and D-112 conflict: no grandparent content_id, so the
# parent's artifact_id cannot be computed). Moved, expectations unchanged.
UNSPECIFIED_IDS = ("grandparent-missing-from-ancestor-lookup",)


def generate() -> dict[str, dict[str, Any]]:
    all_cases = parent_cases()["cases"]
    frozen = [c for c in all_cases if c["id"] not in UNSPECIFIED_IDS]
    unspecified = [c for c in all_cases if c["id"] in UNSPECIFIED_IDS]
    return {
        "parent-versions-unspecified.json": {
            "format": "parent-versions/1",
            "status": "not frozen (not in the 1.1.0 FREEZE.md)",
            "rule": "B-form cases that depend on points D-112 leaves unspecified: the code when a parent's artifact_id cannot be computed; an ancestor_lookup entry with missing fields; where the child's calibration_ref is looked up (parents' envelopes only, or also ancestor_lookup); whether calibration_unknown for a parent uses ancestor_lookup. Same case shape as parent-versions.json. D-113: grandparent-missing-from-ancestor-lookup (D-111 (4) and D-112 conflict) is here, with its expectations unchanged.",
            "cases": unspecified,
        },
        "check-envelope.json": {
            "format": "check-envelope-versioned/1",
            "rule": "check_envelope_versioned(envelope, lookup) returns the set of violation codes in expect.codes (empty = accept); the rule is selected by contract.version; an unsupported version is `unsupported_contract_version`; a version that cannot be read is `schema`",
            **check_cases(),
        },
        "parent-versions.json": {
            "format": "parent-versions/1",
            "rule": "expect.a: check_envelope_versioned(envelope, lookup) (lookup is trusted); expect.b: check_envelope_with_parents(envelope, parents, ancestor_lookup) (the parents are checked with their own version's rule and their content_id is recomputed from their own contract)",
            "cases": frozen,
        },
    }


def _dump(name: str, doc: dict[str, Any]) -> None:
    (VECTORS_V110 / name).parent.mkdir(parents=True, exist_ok=True)
    (VECTORS_V110 / name).write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> None:
    for name, doc in generate().items():
        _dump(name, doc)
        print("wrote", name)


if __name__ == "__main__":
    main()
