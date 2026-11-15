"""nvs.hidden-trajectory 0.1.0: check_hidden_trajectory, HT-01 .. HT-17 and HT-19 (design U5 v0.2, T-U5-01 .. 20).

The material is the accept cases of the U5-3 vectors, broken one item at a time. HT-18 (the binding to the
contract v2) is U5-5: here only its UNVERIFIABLE is checked."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any

import pytest
from contracts import hidden_trajectory as ht
from contracts import ids
from contracts.check import Violation
from contracts.hid_space import SpaceInputError, hid_space
from contracts.hidden_trajectory import HiddenTrajectoryResult, check_hidden_trajectory
from contracts.ic00_versions import check_envelope_versioned
from contracts.schemas import CONTRACTS_DIR
from make_vectors import _env, seal

VEC = json.loads(
    (CONTRACTS_DIR / "nvs/vectors/hidden-trajectory-payload.json").read_text(
        encoding="utf-8"
    )
)
PAYLOADS = {c["id"]: c["payload"] for c in VEC["cases"]}
BLOBS = {u: bytes.fromhex(h) for u, h in VEC["blobs"].items()}
OBS = "obs:" + "a" * 64
MLP, BLOCK, FINAL = (
    "accept-qwen35-mlp-out-15",
    "accept-qwen35-block-out-15",
    "accept-llama-final-norm",
)
_AUTO: Any = object()


def payload_of(case: str = MLP, **edits: Any) -> dict[str, Any]:
    """A copy of an accept payload; ``edits`` keys are dotted paths (``binding__n_gen`` for ``binding.n_gen``)."""
    p = copy.deepcopy(PAYLOADS[case])
    for path, value in edits.items():
        cur: Any = p
        parts = path.split("__")
        for part in parts[:-1]:
            cur = cur[int(part)] if isinstance(cur, list) else cur[part]
        cur[parts[-1]] = value
    result: dict[str, Any] = p
    return result


def space_of(p: dict[str, Any]) -> str | None:
    try:
        return hid_space(
            model_build_id=p["model_build_id"],
            layer=p["layer"],
            row_rule=p["row_rule"],
            compute_environment=p["compute_environment"],
            dimension=p["dimension"],
        )
    except SpaceInputError:
        return None


def envelope_of(
    p: dict[str, Any], *, space_id: Any = _AUTO, **over: Any
) -> dict[str, Any]:
    env: dict[str, Any] = {
        "kind": "observation",
        "producer": {"name": "sensos-inference", "version": "0.1.0", "build": "b"},
        "observation_id": OBS,
        "parents": [],
        "space_id": space_of(p) if space_id is _AUTO else space_id,
        "payload_schema": {"id": "nvs.hidden-trajectory", "version": "0.1.0"},
        "payload": p,
    }
    env.update(over)
    return env


def run(
    p: dict[str, Any] | None = None,
    blobs: Any = _AUTO,
    stored: Any = None,
    **env_kw: Any,
) -> HiddenTrajectoryResult:
    p = payload_of() if p is None else p
    registry = env_kw.pop("registry", None)
    return check_hidden_trajectory(
        envelope_of(p, **env_kw),
        stored,
        BLOBS if blobs is _AUTO else blobs,
        registry=registry,
    )


def codes(result: HiddenTrajectoryResult) -> set[str]:
    return {v.code for v in result.violations}


def blob_ref_for(data: bytes, ref: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(data).hexdigest()
    return {**ref, "sha256": digest, "uri": "blob:sha256:" + digest}


# -------------------------------------------------------------------------------- T-U5-01 .. 03: accept


@pytest.mark.parametrize("case", [FINAL, BLOCK, MLP])
def test_t_u5_01_accept_with_blobs_is_pass_and_only_the_contract_is_unverifiable(
    case: str,
) -> None:
    result = run(payload_of(case))
    assert result.violations == () and result.ok
    assert result.unverifiable == (
        ht.Unverifiable("contract_binding", "contract_not_supplied"),
    )


def test_t_u5_02_accept_without_blobs_lists_what_was_not_checked() -> None:
    result = run(blobs={})
    assert result.ok
    assert set(result.unverifiable) == {
        ht.Unverifiable("token_index_bytes", "blob_not_supplied"),
        ht.Unverifiable("points_bytes", "blob_not_supplied"),
        ht.Unverifiable("contract_binding", "contract_not_supplied"),
    }


def test_t_u5_02_one_blob_missing_lists_only_that_one() -> None:
    p = payload_of()
    only_points = {p["points"]["uri"]: BLOBS[p["points"]["uri"]]}
    assert [u.check for u in run(blobs=only_points).unverifiable] == [
        "token_index_bytes",
        "contract_binding",
    ]


def test_t_u5_03_contract_ref_null_is_contract_absent() -> None:
    result = run(payload_of("accept-contract-ref-null"))
    assert result.ok
    assert ht.Unverifiable("contract_binding", "contract_absent") in result.unverifiable
    assert all(u.reason != "contract_not_supplied" for u in result.unverifiable)


def test_the_other_accept_cases_of_the_vectors() -> None:
    for case in (
        "accept-partly-unknown-provenance",
        "accept-chat-template-not-applicable",
        "accept-layer-zero",
        "accept-finish-reason-length",
    ):
        assert run(payload_of(case)).ok, case


# ---------------------------------------------------------------------- T-U5-04 .. 06: the schema, alone


@pytest.mark.parametrize(
    "edits",
    [
        {"row_rule": "unknown"},
        {"binding__n_in": "unknown"},
        {"final_norm_applied": "unknown"},
        {"raw_ref__trajectory_id": "unknown"},
        {"model_build_id": "unknown"},
        {"compute_environment": "unknown"},
        {"dimension": "unknown"},
        {"length": "unknown"},
        {"dimensions": [4]},
        {"layer": "15"},
        {"layer": True},
        {"layer": "mlp_out"},
        {"layer": None},
        {"layer": -1},
        {"binding__n_in": 0},
    ],
    ids=lambda e: ",".join(f"{k}={v!r}" for k, v in e.items()),
)
def test_t_u5_04_to_06_schema_failure_is_reported_alone(edits: dict[str, Any]) -> None:
    p = payload_of()
    for key, value in edits.items():
        cur = p
        parts = key.split("__")
        for part in parts[:-1]:
            cur = cur[part]
        cur[parts[-1]] = value
    result = run(p)
    assert [v.code for v in result.violations] == ["schema"]
    assert result.violations[0].message.startswith("payload/")
    assert result.unverifiable == ()


def test_schema_failure_stops_before_the_semantic_checks() -> None:
    result = run(
        payload_of(dimensions=[4]),
        space_id="hid:wrong",
        observation_id=None,
        kind="interpretation",
    )
    assert [v.code for v in result.violations] == ["schema"]


# ------------------------------------------------------------------------------------- HT-01 .. HT-03


@pytest.mark.parametrize(
    "env_kw",
    [
        {"kind": "interpretation"},
        {"kind": "outcome"},
        {"producer": {"name": "nvs-kernel", "version": "1", "build": "b"}},
        {"producer": {"name": "nvs-runtime", "version": "1", "build": "b"}},
    ],
    ids=["interpretation", "outcome", "nvs-kernel", "nvs-runtime"],
)
def test_t_u5_20_wrong_kind_or_producer_is_e_traj_kind(env_kw: dict[str, Any]) -> None:
    assert codes(run(**env_kw)) == {"E_TRAJ_KIND"}


def test_t_u5_20_s4_comes_from_the_envelope_layer_not_from_here() -> None:
    """L1 (check_envelope_versioned) gives S4 for sensos-inference + interpretation; HT-01 gives E_TRAJ_KIND."""
    ses = ids.session_id_experiment("sha256:" + "c" * 64, "item-001", "baseline", 0, 7)
    env = _env(
        name="sensos-inference",
        kind="interpretation",
        payload=payload_of(),
        seq=1,
        session=ses,
        obs=OBS,
        space_id=space_of(payload_of()),
    )
    env["contract"]["version"] = "1.1.0"
    env["payload_schema"] = {"id": "nvs.hidden-trajectory", "version": "0.1.0"}
    sealed = seal(env, {})
    assert "S4" in {v.code for v in check_envelope_versioned(sealed, {})}
    assert codes(check_hidden_trajectory(sealed, None, BLOBS)) == {"E_TRAJ_KIND"}
    assert check_envelope_versioned(seal({**env, "kind": "observation"}, {}), {}) == []


def test_ht_02_observation_id_null() -> None:
    assert codes(run(observation_id=None)) == {"E_TRAJ_NO_OBSERVATION"}


def test_ht_03_parents() -> None:
    aid = "art:" + "1" * 64
    ok = [{"role": "generated_text", "ordered": False, "artifact_ids": [aid]}]
    held = {aid: {"envelope": {"observation_id": OBS}}}
    assert run(parents=ok, stored=held).ok
    assert run(parents=[]).ok
    other_role = [{"role": "history", "ordered": False, "artifact_ids": [aid]}]
    assert codes(run(parents=other_role, stored=held)) == {"E_TRAJ_PARENTS"}
    two_ids = [
        {
            "role": "generated_text",
            "ordered": False,
            "artifact_ids": [aid, "art:" + "2" * 64],
        }
    ]
    assert "E_TRAJ_PARENTS" in codes(run(parents=two_ids, stored=held))
    two_roles = [
        *ok,
        {"role": "history", "ordered": False, "artifact_ids": ["art:" + "3" * 64]},
    ]
    assert "E_TRAJ_PARENTS" in codes(run(parents=two_roles, stored=held))


# ------------------------------------------------------------------------------------- HT-04 .. HT-06


@pytest.mark.parametrize(
    "edits",
    [
        {"points__shape": [3, 5]},
        {"points__shape": [2, 4]},
        {"token_index__shape": [4]},
        {"points__shape": [4, 3]},
    ],
)
def test_ht_04_shapes(edits: dict[str, Any]) -> None:
    assert "E_TRAJ_SHAPE" in codes(run(payload_of(**edits)))


def test_ht_04_a_correct_shape_is_not_flagged() -> None:
    assert "E_TRAJ_SHAPE" not in codes(run())


def test_t_u5_07_length_differs_from_n_gen() -> None:
    assert codes(run(payload_of(binding__n_gen=4))) == {"E_TRAJ_ROWS"}
    assert codes(run(payload_of(binding__n_gen=2))) == {"E_TRAJ_ROWS"}


def test_t_u5_07_n_in_zero_is_a_schema_failure_before_it_is_a_rows_failure() -> None:
    assert [v.code for v in run(payload_of(binding__n_in=0)).violations] == ["schema"]


@pytest.mark.parametrize("edits", [{"layer": 15.0}, {"dimension": 4.0}])
def test_ht_05_a_float_that_the_schema_lets_through_is_stopped_here(
    edits: dict[str, Any],
) -> None:
    result = run(payload_of(**edits))
    assert "schema" not in codes(result)
    assert "E_TRAJ_SPACE_INPUT" in codes(result)


def test_ht_05_a_bool_never_reaches_it_the_schema_stops_it_and_hid_space_refuses_it_too() -> (
    None
):
    assert [v.code for v in run(payload_of(layer=True)).violations] == ["schema"]
    assert [v.code for v in run(payload_of(dimension=True)).violations] == ["schema"]
    with pytest.raises(SpaceInputError):
        hid_space(
            model_build_id="m",
            layer=True,
            row_rule="qwen35-mlx-mlp-out/1",
            compute_environment="e",
            dimension=4,
        )


@pytest.mark.parametrize("field", ["model_build_id", "compute_environment"])
def test_ht_05_missing_value_words_in_the_space_materials(field: str) -> None:
    assert [v.code for v in run(payload_of(**{field: "unknown"})).violations] == [
        "schema"
    ]
    result = run(payload_of(**{field: "not_applicable"}))
    assert "E_TRAJ_SPACE_INPUT" in codes(result) and "schema" not in codes(result)


def test_t_u5_11_space_id_differs_is_null_or_the_environment_changed() -> None:
    assert codes(run(space_id="hid:" + "0" * 64)) == {"E_TRAJ_SPACE"}
    assert codes(run(space_id=None)) == {"E_TRAJ_SPACE"}
    p = payload_of()
    stamped = space_of(p)
    assert codes(
        run(payload_of(compute_environment="other-env"), space_id=stamped)
    ) == {"E_TRAJ_SPACE"}
    assert run(p, space_id=stamped).ok


def test_ht_06_layer_type_is_part_of_the_space() -> None:
    """15 and \"15\" are different spaces (D-179 (2)); the payload's own layer is what is recomputed."""
    p = payload_of(BLOCK)
    assert space_of(p) != hid_space(
        model_build_id=p["model_build_id"],
        layer="final_norm",
        row_rule=p["row_rule"],
        compute_environment=p["compute_environment"],
        dimension=p["dimension"],
    )


# ------------------------------------------------------------------------------------- HT-07 .. HT-09


def test_t_u5_09_unregistered_base_rule() -> None:
    assert codes(run(payload_of(row_rule="qwen35-mlx-mlp-out/9"))) == {
        "E_TRAJ_ROW_RULE_UNKNOWN"
    }
    assert codes(run(payload_of(row_rule="mystery-mlx-mlp-out/1"))) == {
        "E_TRAJ_ROW_RULE_UNKNOWN"
    }


@pytest.mark.parametrize(
    "row_rule",
    ["qwen35-mlx-mlp-out/1+rows0+128/1", "all rows of the mlp out", "qwen35-mlx/1"],
)
def test_t_u5_09_window_form_description_and_missing_slug_are_schema_failures(
    row_rule: str,
) -> None:
    assert [v.code for v in run(payload_of(row_rule=row_rule)).violations] == ["schema"]


def test_t_u5_10_kind_and_row_rule_must_agree() -> None:
    assert codes(run(payload_of(row_rule="qwen35-mlx-block-out/1"))) == {
        "E_TRAJ_ROW_RULE_KIND"
    }
    assert codes(run(payload_of(BLOCK, row_rule="qwen35-mlx-mlp-out/1"))) == {
        "E_TRAJ_ROW_RULE_KIND"
    }
    assert codes(run(payload_of(FINAL, row_rule="qwen35-mlx-mlp-out/1"))) >= {
        "E_TRAJ_ROW_RULE_KIND"
    }


def test_t_u5_10_the_registry_kind_is_checked_too() -> None:
    wrong = {
        "qwen35-mlx-mlp-out/1": {"kind": "block_out", "alignment": "decides-next/1"}
    }
    assert codes(run(registry=wrong)) == {"E_TRAJ_ROW_RULE_KIND"}


def test_t_u5_08_alignment_must_be_the_registry_formula() -> None:
    other = {"qwen35-mlx-mlp-out/1": {"kind": "mlp_out", "alignment": "decides-next/2"}}
    assert codes(run(registry=other)) == {"E_TRAJ_ALIGNMENT"}
    assert run().ok  # the real registry says decides-next/1


def test_t_u5_08_a_different_alignment_in_the_payload_is_a_schema_failure() -> None:
    assert [
        v.code for v in run(payload_of(binding__alignment="decides-next/2")).violations
    ] == ["schema"]


# ------------------------------------------------------------------------------------- HT-11 .. HT-14


def test_t_u5_12_layer_and_point_disagree() -> None:
    assert codes(
        run(
            payload_of(
                point="block_out:7",
                kind="block_out",
                row_rule="qwen35-mlx-block-out/1",
                position="L15.block_out",
            )
        )
    ) == {"E_TRAJ_POINT"}
    assert codes(run(payload_of(layer=14))) == {"E_TRAJ_POINT"}


@pytest.mark.parametrize(
    "edits",
    [
        {"kind": "block_out", "row_rule": "qwen35-mlx-block-out/1"},
        {"position": "L15.block_out"},
        {"position": "L14.mlp_out"},
        {"point": "final_norm"},
    ],
)
def test_t_u5_12_kind_or_position_disagree_with_point(edits: dict[str, Any]) -> None:
    assert "E_TRAJ_POINT" in codes(run(payload_of(**edits)))


def test_ht_11_layer_must_be_an_integer_not_its_string() -> None:
    assert "E_TRAJ_POINT" in codes(run(payload_of(FINAL, layer=15)))
    assert "E_TRAJ_POINT" in codes(run(payload_of(layer="final_norm")))


def test_t_u5_13_final_norm_applied() -> None:
    assert codes(run(payload_of(FINAL, final_norm_applied=False))) == {
        "E_TRAJ_FINAL_NORM"
    }
    assert codes(run(payload_of(MLP, final_norm_applied=True))) == {"E_TRAJ_FINAL_NORM"}
    for applied in (True, False):
        assert run(payload_of(BLOCK, final_norm_applied=applied)).ok


def test_t_u5_14_points_sha256_differs_from_raw_ref() -> None:
    assert codes(run(payload_of(raw_ref__trajectory_id="b" * 64))) == {"E_TRAJ_RAW_REF"}


def test_ht_13_uri_hex_differs_is_s34() -> None:
    assert codes(run(payload_of(points__uri="blob:sha256:" + "0" * 64), blobs={})) == {
        "S34"
    }


def test_ht_14_policy_sha256() -> None:
    assert codes(run(payload_of(policy__sha256="c" * 64))) == {"E_TRAJ_POLICY"}
    assert codes(run(payload_of(policy__name="capture-all-rows/2"))) == {
        "E_TRAJ_POLICY"
    }


# ------------------------------------------------------------------------------------------ T-U5-15


def _points_variant(data: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    base = payload_of()
    ref = blob_ref_for(data, base["points"])
    p = payload_of(raw_ref__trajectory_id=ref["sha256"])
    p["points"] = ref
    return p, {**BLOBS, ref["uri"]: data}


def test_t_u5_15_sha256_differs_from_the_bytes_s42() -> None:
    p = payload_of()
    other = struct.pack("<12f", *[float(i) + 1 for i in range(12)])
    assert codes(run(p, blobs={**BLOBS, p["points"]["uri"]: other})) == {"S42"}


def test_t_u5_15_length_is_not_shape_times_four_s43() -> None:
    p, blobs = _points_variant(struct.pack("<11f", *range(11)))
    assert codes(run(p, blobs=blobs)) == {"S43"}


@pytest.mark.parametrize(
    "word", [0x7FC00000, 0xFFC00000, 0x7F800000, 0xFF800000, 0x7FA00000]
)
def test_t_u5_15_nan_and_inf_s44(word: int) -> None:
    good = struct.pack("<12f", *[float(i) for i in range(12)])
    data = good[:8] + struct.pack("<I", word) + good[12:]
    p, blobs = _points_variant(data)
    assert codes(run(p, blobs=blobs)) == {"S44"}


# ------------------------------------------------------------------------------------------ HT-15


@pytest.mark.parametrize("bad", [[0, 1, 3], [1, 2, 3], [0, 0, 1], [2, 1, 0]])
def test_t_u5_16_token_index_values(bad: list[int]) -> None:
    base = payload_of()
    data = struct.pack("<3q", *bad)
    ref = blob_ref_for(data, base["token_index"])
    p = payload_of()
    p["token_index"] = ref
    assert codes(run(p, blobs={**BLOBS, ref["uri"]: data})) == {"E_TRAJ_TOKEN_INDEX"}


def test_t_u5_16_token_index_of_the_wrong_length_is_flagged() -> None:
    base = payload_of()
    data = struct.pack("<2q", 0, 1)
    ref = blob_ref_for(data, base["token_index"])
    p = payload_of()
    p["token_index"] = ref
    assert "E_TRAJ_TOKEN_INDEX" in codes(run(p, blobs={**BLOBS, ref["uri"]: data}))


def test_t_u5_16_a_token_index_whose_sha256_differs_from_its_bytes_is_flagged_by_the_blob_check() -> (
    None
):
    p = payload_of()
    assert "S24" in codes(
        run(
            p,
            blobs={
                **BLOBS,
                p["token_index"]["uri"]: struct.pack("<3q", 0, 1, 2) + b"\x00" * 8,
            },
        )
    )


def test_t_u5_17_unknowns_listed_not_listed_and_not_applicable() -> None:
    assert run(payload_of("accept-partly-unknown-provenance")).ok
    unlisted = payload_of("accept-partly-unknown-provenance", unknowns=[])
    assert codes(run(unlisted)) == {"E_TRAJ_UNKNOWNS"}
    template = payload_of(
        "accept-chat-template-not-applicable",
        unknowns=[
            {"field": "/capture_provenance/chat_template_sha256", "reason": "unknown"}
        ],
    )
    assert codes(run(template)) == {"E_TRAJ_UNKNOWNS"}


def test_ht_15_unknowns_must_be_ascending_unique_and_exact() -> None:
    base = payload_of("accept-partly-unknown-provenance")
    ascending = base["unknowns"]
    assert [u["field"] for u in ascending] == sorted(u["field"] for u in ascending)
    assert codes(
        run(
            payload_of(
                "accept-partly-unknown-provenance", unknowns=list(reversed(ascending))
            )
        )
    ) == {"E_TRAJ_UNKNOWNS"}
    assert codes(
        run(
            payload_of(
                "accept-partly-unknown-provenance", unknowns=[*ascending, ascending[0]]
            )
        )
    ) == {"E_TRAJ_UNKNOWNS"}
    extra = [
        *ascending,
        {"field": "/capture_provenance/tokenizer_sha256", "reason": "unknown"},
    ]
    assert codes(
        run(
            payload_of(
                "accept-partly-unknown-provenance",
                unknowns=sorted(extra, key=lambda u: u["field"]),
            )
        )
    ) == {"E_TRAJ_UNKNOWNS"}
    assert codes(
        run(payload_of("accept-partly-unknown-provenance", unknowns=[ascending[0]]))
    ) == {"E_TRAJ_UNKNOWNS"}


def test_ht_15_a_nested_unknown_is_found_by_its_json_pointer() -> None:
    p = payload_of("accept-runtime-backend-unknown")
    assert codes(run(p)) == {"E_TRAJ_UNKNOWNS"}
    p["unknowns"] = [
        {"field": "/capture_provenance/runtime/backend", "reason": "not_recorded"}
    ]
    assert run(p).ok


def test_ht_15_unknown_outside_state_dtype_and_provenance_is_refused() -> None:
    p = payload_of(
        policy__name="unknown",
        policy__sha256=hashlib.sha256(b"unknown").hexdigest(),
        unknowns=[{"field": "/policy/name", "reason": "unknown"}],
    )
    result = run(p)
    assert (
        codes(result) == {"E_TRAJ_UNKNOWNS"}
        and "cannot be" in result.violations[0].message
    )


# ------------------------------------------------------------------------------- HT-19 and T-U5-18


def _parent_world(parent_obs: str = OBS) -> tuple[dict[str, Any], str, dict[str, Any]]:
    aid = "art:" + "1" * 64
    parents = [{"role": "generated_text", "ordered": False, "artifact_ids": [aid]}]
    return (
        {"parents": parents},
        aid,
        {aid: {"envelope": {"observation_id": parent_obs}}},
    )


def test_t_u5_18_stored_parent_with_the_same_observation_is_accepted() -> None:
    kw, _aid, stored = _parent_world()
    assert run(stored=stored, **kw).ok


def test_t_u5_18_parent_not_stored_is_parent_unknown() -> None:
    kw, aid, _ = _parent_world()
    result = run(stored={}, **kw)
    assert codes(result) == {"parent_unknown"} and result.violations[0].message == aid
    assert codes(run(stored=None, **kw)) == {"parent_unknown"}


def test_t_u5_18_parent_with_another_observation_id_is_s8() -> None:
    kw, _aid, stored = _parent_world(parent_obs="obs:" + "b" * 64)
    assert codes(run(stored=stored, **kw)) == {"S8"}


def test_t_u5_18_observation_id_null_with_a_parent_has_both_codes() -> None:
    kw, _aid, stored = _parent_world()
    assert codes(run(stored=stored, observation_id=None, **kw)) == {
        "E_TRAJ_NO_OBSERVATION",
        "S8",
    }


def test_ht_19_a_stored_envelope_may_be_given_bare() -> None:
    kw, aid, _ = _parent_world()
    assert run(stored={aid: {"observation_id": OBS}}, **kw).ok


# -------------------------------------------------------------------------------- collecting, not stopping


def test_all_violations_are_collected_not_just_the_first() -> None:
    p = payload_of(
        raw_ref__trajectory_id="b" * 64,
        policy__sha256="c" * 64,
        final_norm_applied=True,
        binding__n_gen=4,
        row_rule="qwen35-mlx-mlp-out/9",
    )
    result = run(
        p, space_id="hid:" + "0" * 64, observation_id=None, kind="interpretation"
    )
    assert codes(result) == {
        "E_TRAJ_KIND",
        "E_TRAJ_NO_OBSERVATION",
        "E_TRAJ_SPACE",
        "E_TRAJ_ROW_RULE_UNKNOWN",
        "E_TRAJ_ROWS",
        "E_TRAJ_FINAL_NORM",
        "E_TRAJ_RAW_REF",
        "E_TRAJ_POLICY",
    }
    assert not result.ok


def test_checks_after_a_failed_space_are_still_run() -> None:
    result = run(payload_of(layer=15.0, binding__n_gen=4))
    assert {"E_TRAJ_SPACE_INPUT", "E_TRAJ_ROWS", "E_TRAJ_POINT"} <= codes(result)


def test_blob_checks_run_next_to_the_other_failures() -> None:
    p = payload_of(policy__sha256="c" * 64)
    other = struct.pack("<12f", *[float(i) + 1 for i in range(12)])
    result = run(p, blobs={**BLOBS, p["points"]["uri"]: other})
    assert codes(result) == {"E_TRAJ_POLICY", "S42"}


# -------------------------------------------------------------------------------- catalogue and imports


def test_the_unverifiable_catalogue_is_next_to_the_checker() -> None:
    assert set(ht.UNVERIFIABLE_CATALOG) == {
        ("nvs.hidden-trajectory", "points_bytes", "blob_not_supplied"),
        ("nvs.hidden-trajectory", "token_index_bytes", "blob_not_supplied"),
        ("nvs.hidden-trajectory", "contract_binding", "contract_not_supplied"),
        ("nvs.hidden-trajectory", "contract_binding", "contract_absent"),
        ("nvs.hidden-trajectory", "contract_binding.<field>", "contract_field_unknown"),
        ("msr.trajectory-window", "window_rows", "raw_not_in_artifact"),
        ("msr.trajectory-window", "window_space_derivation", "rule_not_derivable"),
    }
    produced = {(u.check, u.reason) for u in run(blobs={}).unverifiable} | {
        (u.check, u.reason)
        for u in run(payload_of("accept-contract-ref-null")).unverifiable
    }
    assert produced <= {(c, r) for _s, c, r in ht.UNVERIFIABLE_CATALOG}


def test_the_checker_imports_no_product_package() -> None:
    path = Path(ht.__file__)
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    assert roots <= set(sys.stdlib_module_names) | {
        "jsonschema",
        "contracts",
        "__future__",
    }


def test_hidden_trajectory_result_ok_means_no_violations() -> None:
    assert HiddenTrajectoryResult().ok
    assert HiddenTrajectoryResult(unverifiable=(ht.Unverifiable("x", "y"),)).ok
    assert not HiddenTrajectoryResult(violations=(Violation("c", "m"),)).ok
