"""HT-20 (T-U5-W01 .. W04): the space of an msr.trajectory-window 0.10.0 is derived again from its hidden-trajectory parent.

The window is the IC-02 0.10.0 accept case ``accept-rows-head`` with its parent replaced by a U5-3 hidden trajectory."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from contracts import gate, ic02_window
from contracts.gate_nvs import check_nvs_payload
from contracts.hid_space import hid_space
from contracts.hidden_trajectory import HiddenTrajectoryResult, Unverifiable
from contracts.hidden_trajectory_window import check_window_space, derived_row_rule
from contracts.schemas import CONTRACTS_DIR
from test_hidden_trajectory import BLOCK, MLP, envelope_of, payload_of

WINDOWS = json.loads(
    (CONTRACTS_DIR / "msr/vectors/window-rows.json").read_text(encoding="utf-8")
)
HEAD = next(c for c in WINDOWS["cases"] if c["id"] == "accept-rows-head")
PARENT_ID = HEAD["envelope"]["parents"][0]["artifact_ids"][0]

SPACE_E = "hid:e9b93a52591b9a848190bc0439561a4eb91915970bf7c7cd192758fabe433f90"
SPACE_F = "hid:d4dc7ca0c57d63f235ff6382df3fb44246021ec7a1fbd9b4966a8c6078bc356d"
NOT_DERIVABLE = (Unverifiable("window_space_derivation", "rule_not_derivable"),)


def parent_payload(**edits: Any) -> dict[str, Any]:
    """Design 2.3 material A: qwen35 block-out, layer 15, mlx-4bit, 2560."""
    base: dict[str, Any] = {
        "model_build_id": "qwen35-4b-mlx-4bit",
        "compute_environment": "mlx-4bit",
        "dimension": 2560,
        "layer": 15,
    }
    base.update(edits)
    return payload_of(BLOCK, **base)


def space_for(
    parent: dict[str, Any], start: int, length: int = 128, **over: Any
) -> str:
    args: dict[str, Any] = {
        "model_build_id": parent["model_build_id"],
        "layer": parent["layer"],
        "compute_environment": parent["compute_environment"],
        "dimension": parent["dimension"],
        "row_rule": derived_row_rule(parent["row_rule"], start, length),
    }
    args.update(over)
    return hid_space(**args)


def window_of(
    parent: dict[str, Any],
    start: int = 0,
    length: int = 128,
    *,
    rule: str = "rows",
    space_id: Any = ...,
    **payload_edits: Any,
) -> dict[str, Any]:
    env: dict[str, Any] = copy.deepcopy(HEAD["envelope"])
    p = env["payload"]
    p.update(
        model_build_id=parent["model_build_id"],
        layer=parent["layer"],
        dimension=parent["dimension"],
        source="T-hid",
    )
    p["window"].update(rule=rule, start=start, length=length)
    p["origin"].update(
        trajectory_id=parent["raw_ref"]["trajectory_id"],
        position=parent["position"],
        length=parent["length"],
    )
    p.update(payload_edits)
    env["space_id"] = space_for(parent, start, length) if space_id is ... else space_id
    return env


def stored_of(parent: dict[str, Any], **env_over: Any) -> dict[str, Any]:
    return {PARENT_ID: {"envelope": envelope_of(parent, **env_over)}}


def run(
    parent: dict[str, Any] | None = None,
    start: int = 0,
    length: int = 128,
    **kw: Any,
) -> HiddenTrajectoryResult:
    parent = parent_payload() if parent is None else parent
    return check_window_space(window_of(parent, start, length, **kw), stored_of(parent))


def codes(r: HiddenTrajectoryResult) -> list[str]:
    return [v.code for v in r.violations]


# --------------------------------------------------------------------------------------------- W01


def test_the_design_samples_e_and_f_are_what_the_window_derives() -> None:
    parent = parent_payload()
    assert space_for(parent, 0) == SPACE_E
    assert space_for(parent, 128) == SPACE_F
    assert (
        derived_row_rule("qwen35-mlx-block-out/1", 0, 128)
        == "qwen35-mlx-block-out/1+rows0+128/1"
    )
    assert (
        derived_row_rule("qwen35-mlx-block-out/1", 128, 128)
        == "qwen35-mlx-block-out/1+rows128+128/1"
    )


@pytest.mark.parametrize(
    "start,space", [(0, SPACE_E), (128, SPACE_F)], ids=["E-start-0", "F-start-128"]
)
def test_t_u5_w01_samples_e_and_f_pass_w1_to_w4(start: int, space: str) -> None:
    parent = parent_payload()
    result = check_window_space(
        window_of(parent, start, space_id=space), stored_of(parent)
    )
    assert result == HiddenTrajectoryResult((), ())


def test_prefix_rows_and_rows_give_the_same_derived_space() -> None:
    parent = parent_payload()
    prefix = window_of(parent, 0, 128, rule="prefix_rows")
    rows = window_of(parent, 0, 128, rule="rows")
    assert prefix["space_id"] == rows["space_id"] == SPACE_E
    for env in (prefix, rows):
        assert check_window_space(env, stored_of(parent)) == HiddenTrajectoryResult()


def test_the_other_kinds_derive_too() -> None:
    for case in (MLP,):
        parent = payload_of(case)
        assert run(parent).ok and run(parent, 5, 7).ok


# --------------------------------------------------------------------------------------------- W02


def test_t_u5_w02_a_different_kind() -> None:
    parent = payload_of(MLP, layer=15)
    other = parent_payload()  # block-out: a space of another kind
    result = check_window_space(
        window_of(parent, space_id=space_for(other, 0)), stored_of(parent)
    )
    assert codes(result) == ["E_WIN_SPACE"]


def test_t_u5_w02_no_position_the_parents_own_space() -> None:
    parent = parent_payload()
    own = envelope_of(parent)["space_id"]
    assert codes(run(parent, space_id=own)) == ["E_WIN_SPACE"]


def test_t_u5_w02_a_wrong_position() -> None:
    parent = parent_payload()
    result = run(parent, 448, 128, space_id=space_for(parent, 0, 128))
    assert codes(result) == ["E_WIN_SPACE"]
    assert codes(run(parent, 0, 64, space_id=space_for(parent, 0, 128))) == [
        "E_WIN_SPACE"
    ]


def test_t_u5_w02_a_different_compute_environment() -> None:
    parent = parent_payload()
    other = space_for(parent, 0, compute_environment="cuda-fp16")
    assert codes(run(parent, space_id=other)) == ["E_WIN_SPACE"]


@pytest.mark.parametrize("space_id", [None, "SW-head", "hid:" + "0" * 64])
def test_w4_a_null_or_foreign_space_id_fails(space_id: Any) -> None:
    assert codes(run(space_id=space_id)) == ["E_WIN_SPACE"]


# --------------------------------------------------------------------------------------------- W03


@pytest.mark.parametrize(
    "field,value",
    [("model_build_id", "other-model"), ("layer", 14), ("dimension", 8)],
)
def test_t_u5_w03_a_field_differs_from_the_parent(field: str, value: Any) -> None:
    result = run(**{field: value})
    assert (
        codes(result) == ["E_WIN_PARENT_FIELDS"]
        and field in result.violations[0].message
    )
    assert result.unverifiable == ()


def test_w1_layer_15_and_the_string_15_are_different() -> None:
    assert codes(run(layer="15")) == ["E_WIN_PARENT_FIELDS"]
    parent = payload_of(MLP, layer="final_norm")
    assert codes(run(parent, layer=15)) == ["E_WIN_PARENT_FIELDS"]
    assert codes(run(parent, layer=None)) == ["E_WIN_PARENT_FIELDS"]
    assert codes(run(parent, layer=True)) == ["E_WIN_PARENT_FIELDS"]


def test_w1_source_must_be_t_hid_when_the_parent_is_a_hidden_trajectory() -> None:
    assert codes(run(source="T-tok")) == ["E_WIN_PARENT_FIELDS"]


def test_all_violations_are_collected() -> None:
    parent = parent_payload()
    result = run(parent, layer="15", model_build_id="x", space_id=SPACE_F)
    assert codes(result) == [
        "E_WIN_PARENT_FIELDS",
        "E_WIN_PARENT_FIELDS",
        "E_WIN_SPACE",
    ]


# --------------------------------------------------------------------------------------------- W04


def test_t_u5_w04_a_parent_row_rule_that_is_a_description() -> None:
    parent = parent_payload(row_rule="final-norm of the last layer of Llama 3.1")
    result = check_window_space(window_of(parent, space_id=SPACE_E), stored_of(parent))
    assert result.violations == () and result.unverifiable == NOT_DERIVABLE


def test_t_u5_w04_a_parent_row_rule_that_is_already_a_window_rule() -> None:
    parent = parent_payload(row_rule="qwen35-mlx-block-out/1+rows0+128/1")
    result = check_window_space(window_of(parent, space_id=SPACE_E), stored_of(parent))
    assert result.violations == () and result.unverifiable == NOT_DERIVABLE


def test_t_u5_w04_a_parent_that_is_not_a_hidden_trajectory() -> None:
    parent = parent_payload()
    envelope = window_of(parent)
    for schema in (
        {"id": "msr.trajectory-window", "version": "0.10.0"},
        {"id": "nvs.hidden-trajectory", "version": "0.2.0"},
        {"id": "nvs.other", "version": "0.1.0"},
    ):
        held = {PARENT_ID: {"envelope": envelope_of(parent, payload_schema=schema)}}
        result = check_window_space(envelope, held)
        assert result == HiddenTrajectoryResult((), NOT_DERIVABLE), schema


def test_the_parent_cannot_be_fetched_returns_early_as_unverifiable() -> None:
    envelope = window_of(parent_payload())
    helds: list[Any] = [None, {}, {"art:other": {"envelope": {}}}]
    for held in helds:
        assert check_window_space(envelope, held) == HiddenTrajectoryResult(
            (), NOT_DERIVABLE
        )
    two = copy.deepcopy(envelope)
    two["parents"].append(
        {
            "artifact_ids": ["art:" + "2" * 64],
            "ordered": False,
            "role": "source_trajectory",
        }
    )
    assert (
        check_window_space(two, stored_of(parent_payload())).unverifiable
        == NOT_DERIVABLE
    )
    assert check_window_space(two, stored_of(parent_payload())).violations == ()


def test_a_parent_whose_materials_make_no_space_is_unverifiable() -> None:
    parent = parent_payload(layer=True)
    result = check_window_space(window_of(parent, space_id=SPACE_E), stored_of(parent))
    assert result.unverifiable == NOT_DERIVABLE


# ------------------------------------------------------------------------------------------ W-2


def test_w2_a_base_form_that_is_not_in_the_registry_fails() -> None:
    parent = parent_payload(row_rule="unknown-mlx-block-out/1")
    result = check_window_space(window_of(parent), stored_of(parent))
    assert codes(result) == [
        "E_WIN_PARENT_ROW_RULE"
    ]  # W-3 and W-4 are still made and agree


def test_w2_the_registry_can_be_given() -> None:
    parent = parent_payload(row_rule="unknown-mlx-block-out/1")
    registry = {
        "unknown-mlx-block-out/1": {"kind": "block_out", "alignment": "decides-next/1"}
    }
    assert check_window_space(
        window_of(parent), stored_of(parent), registry=registry
    ).ok


def test_w2_the_llama_rule_is_registered() -> None:
    parent = payload_of("accept-llama-final-norm")
    assert parent["row_rule"] == "llama31-mlx-final-norm/1"
    assert run(parent).ok


# -------------------------------------------------------------------------------- scope and IC-02


def test_other_schemas_and_versions_give_an_empty_result() -> None:
    parent = parent_payload()
    base = window_of(parent, space_id=None)
    for schema in (
        {"id": "msr.trajectory-window", "version": "0.9.0"},
        {"id": "msr.geometry-measurement", "version": "0.10.0"},
        {"id": "nvs.hidden-trajectory", "version": "0.1.0"},
    ):
        env = {**base, "payload_schema": schema}
        assert check_window_space(env, stored_of(parent)) == HiddenTrajectoryResult()


@pytest.mark.parametrize(
    "case", WINDOWS["cases"], ids=[c["id"] for c in WINDOWS["cases"]]
)
def test_check_nvs_payload_for_msr_windows_is_exactly_gate_check_payload(
    case: dict[str, Any],
) -> None:
    blobs = {u: bytes.fromhex(h) for u, h in WINDOWS["blobs"].items()}
    got = check_nvs_payload(case["envelope"], case["stored"], blobs)
    assert isinstance(got, list)
    assert got == gate.check_payload(case["envelope"], case["stored"], blobs)


def test_calling_check_window_space_does_not_change_the_ic02_result() -> None:
    parent = parent_payload()
    envelope, stored = window_of(parent), stored_of(parent)
    before = ic02_window.check_window(envelope, stored, {})
    snap = copy.deepcopy((envelope, stored))
    check_window_space(envelope, stored)
    assert (envelope, stored) == snap
    assert ic02_window.check_window(envelope, stored, {}) == before
    assert check_nvs_payload(envelope, stored, {}) == gate.check_payload(
        envelope, stored, {}
    )


def test_the_ic02_vectors_do_not_change_either() -> None:
    for case in WINDOWS["cases"]:
        before = gate.check_payload(case["envelope"], case["stored"], {})
        check_window_space(case["envelope"], case["stored"])
        assert gate.check_payload(case["envelope"], case["stored"], {}) == before
