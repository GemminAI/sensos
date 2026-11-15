"""HT-18: the binding of an nvs.hidden-trajectory envelope to a RawObservationContract v2, through ``contract_facts``
(design U5 v0.2 5.3, T-U5-C01 .. C14). The facts are built from the payload (so they agree with it) and then broken."""

from __future__ import annotations

import copy
import inspect
import json
from typing import Any

import pytest
from contracts import gate
from contracts import hidden_trajectory as ht
from contracts.contract_facts import ContractFactsError, validate_contract_facts
from contracts.gate_nvs import check_nvs_payload
from contracts.hid_space import hid_space_id, hid_space_materials
from contracts.hidden_trajectory import (
    HiddenTrajectoryResult,
    Unverifiable,
    check_hidden_trajectory,
)
from contracts.schemas import CONTRACTS_DIR
from test_hidden_trajectory import (
    BLOBS,
    BLOCK,
    FINAL,
    MLP,
    PAYLOADS,
    VEC,
    envelope_of,
    payload_of,
)

SAMPLE = json.loads(
    (CONTRACTS_DIR / "nvs/vectors/contract-facts-from-u4.json").read_text(
        encoding="utf-8"
    )
)
HEX_OTHER = "e" * 64


def facts_of(p: dict[str, Any]) -> dict[str, Any]:
    """contract_facts that agree with the payload ``p`` in every field HT-18 compares."""
    prov = p["capture_provenance"]
    space = hid_space_materials(
        model_build_id=p["model_build_id"],
        layer=p["layer"],
        row_rule=p["row_rule"],
        compute_environment=p["compute_environment"],
        dimension=p["dimension"],
    )
    ref = p["contract_ref"] or {
        "name": "RawObservationContract",
        "version": 2,
        "contract_sha256": "9" * 64,
    }
    return {
        "facts_version": "nvs.contract-facts/1",
        "contract": dict(ref),
        "synthetic": False,
        "binding": {
            "alignment": p["binding"]["alignment"],
            "n_in": p["binding"]["n_in"],
            "n_gen": p["binding"]["n_gen"],
            "finish_reason": p["binding"]["finish_reason"],
            "tokenizer_sha256": prov["tokenizer_sha256"],
            "chat_template_sha256": prov["chat_template_sha256"],
            "prompt_ids_sha256": prov["prompt_ids_sha256"],
            "gen_token_ids_sha256": prov["gen_token_ids_sha256"],
        },
        "origin": {
            "model_build_id": p["model_build_id"],
            "compute_environment": p["compute_environment"],
            "weights_sha256": prov["weights_sha256"],
        },
        "positions": {
            p["point"]: {
                "trajectory_id": p["raw_ref"]["trajectory_id"],
                "row_rule": p["row_rule"],
                "dimension": p["dimension"],
                "final_norm_applied": p["final_norm_applied"],
                "stored_range": {
                    "steps": p["length"],
                    "first_row_pos": p["binding"]["n_in"] - 1,
                },
                "space": space,
            }
        },
    }


def run18(
    p: dict[str, Any] | None = None, facts: Any = ..., blobs: Any = ..., **env_kw: Any
) -> HiddenTrajectoryResult:
    p = payload_of() if p is None else p
    facts = facts_of(p) if facts is ... else facts
    return check_hidden_trajectory(
        envelope_of(p, **env_kw),
        None,
        BLOBS if blobs is ... else blobs,
        contract_facts=facts,
    )


def codes(r: HiddenTrajectoryResult) -> list[str]:
    return [v.code for v in r.violations]


def facts_edit(
    path: str, value: Any, p: dict[str, Any] | None = None
) -> dict[str, Any]:
    facts = facts_of(payload_of() if p is None else p)
    cur: Any = facts
    parts = path.split(".")
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = value
    return facts


POINT = "mlp_out:15"
ACCEPT = [c["id"] for c in VEC["cases"] if c["expect"]["result"] == "accept"]


# ------------------------------------------------------------------------------------------- C01, C13


@pytest.mark.parametrize("case", [FINAL, BLOCK, MLP])
def test_t_u5_c01_correct_facts_pass_all_of_18a_to_18g(case: str) -> None:
    result = run18(payload_of(case))
    assert result.violations == () and result.unverifiable == ()


def test_t_u5_c13_no_facts_is_contract_not_supplied() -> None:
    result = check_hidden_trajectory(envelope_of(payload_of()), None, BLOBS)
    assert result.ok and result.unverifiable == (
        Unverifiable("contract_binding", "contract_not_supplied"),
    )


def test_t_u5_c13_contract_ref_null_is_contract_absent_even_with_facts() -> None:
    p = payload_of("accept-contract-ref-null")
    result = run18(p)
    assert result.ok and result.unverifiable == (
        Unverifiable("contract_binding", "contract_absent"),
    )


# ----------------------------------------------------------------------------------------------- 18a


def test_t_u5_c02_contract_sha256_one_digit_off() -> None:
    sha = payload_of()["contract_ref"]["contract_sha256"]
    other = sha[:-1] + ("0" if sha[-1] != "0" else "1")
    result = run18(facts=facts_edit("contract.contract_sha256", other))
    assert (
        codes(result) == ["E_TRAJ_CONTRACT"] and "18a" in result.violations[0].message
    )


def test_t_u5_c02_contract_name_differs() -> None:
    result = run18(facts=facts_edit("contract.name", "RawObservationContractV2"))
    assert codes(result) == ["E_TRAJ_CONTRACT"]


def test_t_u5_c02_version_3_cannot_get_past_the_schema_or_the_shape_check() -> None:
    assert [
        v.code
        for v in run18(
            payload_of(contract_ref__version=3), facts=facts_of(payload_of())
        ).violations
    ] == ["schema"]
    with pytest.raises(ContractFactsError):
        run18(facts=facts_edit("contract.version", 3))


# ----------------------------------------------------------------------------------------------- 18b


def test_t_u5_c03_the_point_is_not_among_the_positions() -> None:
    facts = facts_of(payload_of())
    facts["positions"] = {"block_out:7": facts["positions"][POINT]}
    result = run18(facts=facts)
    assert (
        codes(result) == ["E_TRAJ_CONTRACT"] and "18b" in result.violations[0].message
    )  # 18c and 18e are not run


def test_18b_a_missing_point_still_runs_18a_18d_18f() -> None:
    facts = facts_of(payload_of())
    facts["positions"] = {"block_out:7": facts["positions"][POINT]}
    facts["contract"]["contract_sha256"] = HEX_OTHER
    facts["binding"]["finish_reason"] = (
        "length" if payload_of()["binding"]["finish_reason"] == "eos" else "eos"
    )
    facts["origin"]["weights_sha256"] = HEX_OTHER
    result = run18(facts=facts)
    assert codes(result) == ["E_TRAJ_CONTRACT"] * 4
    assert {m.message.split()[0] for m in result.violations} == {
        "18a",
        "18b",
        "18d",
        "18f",
    }


# ----------------------------------------------------------------------------------------------- 18c


@pytest.mark.parametrize(
    "field,value",
    [
        ("trajectory_id", HEX_OTHER),
        ("row_rule", "qwen35-mlx-block-out/1"),
        ("dimension", 5),
        ("final_norm_applied", True),
    ],
)
def test_t_u5_c04_one_position_field_differs(field: str, value: Any) -> None:
    result = run18(facts=facts_edit(f"positions.{POINT}.{field}", value))
    assert (
        codes(result) == ["E_TRAJ_CONTRACT"] and "18c" in result.violations[0].message
    )


@pytest.mark.parametrize(
    "field,value",
    [("steps", 4), ("steps", 2), ("first_row_pos", 3), ("first_row_pos", 5)],
)
def test_t_u5_c05_stored_range(field: str, value: int) -> None:
    result = run18(facts=facts_edit(f"positions.{POINT}.stored_range.{field}", value))
    assert (
        codes(result) == ["E_TRAJ_CONTRACT"]
        and "stored_range" in result.violations[0].message
    )


def test_18c_first_row_pos_is_n_in_minus_one() -> None:
    p = payload_of()
    assert (
        facts_of(p)["positions"][POINT]["stored_range"]["first_row_pos"]
        == p["binding"]["n_in"] - 1
    )
    assert run18(p).ok


# ----------------------------------------------------------------------------------------------- 18d


@pytest.mark.parametrize(
    "field,value",
    [
        ("alignment", "decides-next/2"),
        ("n_in", 6),
        ("n_gen", 4),
        ("finish_reason", "length"),
    ],
)
def test_t_u5_c06_one_binding_field_differs(field: str, value: Any) -> None:
    result = run18(facts=facts_edit(f"binding.{field}", value))
    assert (
        codes(result) == ["E_TRAJ_CONTRACT"] and "18d" in result.violations[0].message
    )


# ----------------------------------------------------------------------------------------------- 18e


def test_t_u5_c07_the_contracts_space_differs_from_the_envelopes_space_id() -> None:
    for key, value in (
        ("compute_environment", "other-env"),
        ("model_build_id", "other-model"),
        ("layer", 14),
        ("dimension", 8),
    ):
        result = run18(facts=facts_edit(f"positions.{POINT}.space.{key}", value))
        assert (
            codes(result) == ["E_TRAJ_CONTRACT"]
            and "18e" in result.violations[0].message
        ), key


def test_18e_a_space_that_cannot_be_computed_is_a_failure_too() -> None:
    result = run18(
        facts=facts_edit(
            f"positions.{POINT}.space.space_rule", "nvs.hidden-trajectory.space/2"
        )
    )
    assert (
        codes(result) == ["E_TRAJ_CONTRACT"]
        and "cannot be computed" in result.violations[0].message
    )


def test_18e_the_three_spaces_agree_when_payload_envelope_and_contract_do() -> None:
    p = payload_of()
    facts = facts_of(p)
    assert (
        hid_space_id(facts["positions"][POINT]["space"]) == envelope_of(p)["space_id"]
    )
    assert run18(p, facts=facts).ok


# ----------------------------------------------------------------------------------------------- 18f


@pytest.mark.parametrize(
    "path",
    [
        "origin.weights_sha256",
        "binding.tokenizer_sha256",
        "binding.chat_template_sha256",
        "binding.prompt_ids_sha256",
        "binding.gen_token_ids_sha256",
    ],
)
def test_t_u5_c08_one_provenance_hash_differs_when_both_are_real(path: str) -> None:
    result = run18(facts=facts_edit(path, HEX_OTHER))
    assert (
        codes(result) == ["E_TRAJ_CONTRACT"] and "18f" in result.violations[0].message
    )
    assert result.unverifiable == ()


# --------------------------------------------------------------------------------------- C09 and C10


@pytest.mark.parametrize(
    "path,field",
    [
        ("origin.weights_sha256", "weights_sha256"),
        (f"positions.{POINT}.trajectory_id", "trajectory_id"),
    ],
)
def test_t_u5_c09_unknown_on_the_contract_side_is_unverifiable_not_a_failure(
    path: str, field: str
) -> None:
    result = run18(facts=facts_edit(path, "unknown"))
    assert result.violations == () and result.ok
    assert result.unverifiable == (
        Unverifiable(f"contract_binding.{field}", "contract_field_unknown"),
    )


def test_t_u5_c09_unknown_on_the_payload_side_is_unverifiable_too() -> None:
    p = payload_of(
        "accept-partly-unknown-provenance"
    )  # weights_sha256 is "unknown" in the payload
    result = run18(p)
    assert result.ok
    assert result.unverifiable == (
        Unverifiable("contract_binding.weights_sha256", "contract_field_unknown"),
    )


def test_t_u5_c09_all_the_contract_side_unknowns_at_once() -> None:
    facts = facts_of(payload_of())
    facts["origin"]["weights_sha256"] = "unknown"
    facts["binding"].update(n_in="unknown", n_gen="unknown", tokenizer_sha256="unknown")
    facts["positions"][POINT].update(
        trajectory_id="unknown", final_norm_applied="unknown"
    )
    facts["positions"][POINT]["stored_range"].update(
        steps="unknown", first_row_pos="unknown"
    )
    result = run18(facts=facts)
    assert result.violations == ()
    assert {u.check for u in result.unverifiable} == {
        "contract_binding.weights_sha256",
        "contract_binding.n_in",
        "contract_binding.n_gen",
        "contract_binding.tokenizer_sha256",
        "contract_binding.trajectory_id",
        "contract_binding.final_norm_applied",
        "contract_binding.stored_range.steps",
        "contract_binding.stored_range.first_row_pos",
    }
    assert {u.reason for u in result.unverifiable} == {"contract_field_unknown"}


def test_t_u5_c10_not_applicable_against_a_real_value_fails() -> None:
    na = payload_of("accept-chat-template-not-applicable")
    facts = facts_of(na)
    facts["binding"]["chat_template_sha256"] = HEX_OTHER
    result = run18(na, facts=facts)
    assert (
        codes(result) == ["E_TRAJ_CONTRACT"]
        and "chat_template_sha256" in result.violations[0].message
    )
    real = payload_of()
    facts = facts_of(real)
    facts["binding"]["chat_template_sha256"] = "not_applicable"
    assert codes(run18(real, facts=facts)) == ["E_TRAJ_CONTRACT"]


def test_t_u5_c10_two_not_applicable_agree() -> None:
    na = payload_of("accept-chat-template-not-applicable")
    assert run18(na).violations == () and run18(na).unverifiable == ()


# ----------------------------------------------------------------------------------------- C11, 18g


def test_t_u5_c11_synthetic_facts_are_refused() -> None:
    result = run18(facts=facts_edit("synthetic", True))
    assert codes(result) == ["E_TRAJ_SYNTHETIC"] and not result.ok


def test_18g_synthetic_is_refused_also_when_contract_ref_is_null() -> None:
    p = payload_of("accept-contract-ref-null")
    facts = facts_of(p)
    facts["synthetic"] = True
    result = run18(p, facts=facts)
    assert codes(result) == ["E_TRAJ_SYNTHETIC"]
    assert result.unverifiable == (Unverifiable("contract_binding", "contract_absent"),)


def test_18g_synthetic_does_not_hide_the_other_failures() -> None:
    facts = facts_edit("binding.finish_reason", "length")
    facts["synthetic"] = True
    assert sorted(codes(run18(facts=facts))) == ["E_TRAJ_CONTRACT", "E_TRAJ_SYNTHETIC"]


def test_18g_synthetic_false_is_not_a_violation() -> None:
    assert run18().ok


# ----------------------------------------------------------------------------------------------- C12


@pytest.mark.parametrize(
    "mutate",
    [
        lambda f: f.update(extra=1),
        lambda f: f["contract"].update(version=3),
        lambda f: f["positions"][POINT]["space"].pop("space_rule"),
        lambda f: f["positions"][POINT]["space"].update(layer="15"),
        lambda f: f.pop("binding"),
    ],
    ids=[
        "extra-key",
        "version-3",
        "space-5-keys",
        "layer-string-15",
        "missing-binding",
    ],
)
def test_t_u5_c12_wrong_shape_is_raised_not_reported(mutate: Any) -> None:
    facts = facts_of(payload_of())
    mutate(facts)
    with pytest.raises(ContractFactsError) as info:
        run18(facts=facts)
    assert info.value.code == "gate_internal_error"
    with pytest.raises(ContractFactsError):
        check_nvs_payload(envelope_of(payload_of()), None, BLOBS, contract_facts=facts)


def test_t_u5_c12_it_is_raised_even_when_the_payload_would_fail_the_schema() -> None:
    facts = facts_of(payload_of())
    facts["extra"] = 1
    with pytest.raises(ContractFactsError):
        run18(payload_of(dimensions=[4]), facts=facts)


# ------------------------------------------------------------------------------ nothing else changes


def test_without_facts_the_result_is_that_of_u5_4() -> None:
    for case in ACCEPT:
        p = payload_of(case)
        env = envelope_of(p)
        assert check_hidden_trajectory(
            env, None, BLOBS, contract_facts=None
        ) == check_hidden_trajectory(env, None, BLOBS)


def test_without_facts_the_unverifiable_list_is_that_of_u5_4_in_order() -> None:
    result = check_hidden_trajectory(envelope_of(payload_of()), None, {})
    assert [u.check for u in result.unverifiable] == [
        "token_index_bytes",
        "points_bytes",
        "contract_binding",
    ]


def test_the_signatures_keep_their_order_and_the_new_argument_is_keyword_only() -> None:
    sig = inspect.signature(check_hidden_trajectory)
    assert list(sig.parameters) == [
        "envelope",
        "stored",
        "blobs",
        "registry",
        "contract_facts",
    ]
    assert sig.parameters["contract_facts"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["registry"].kind is inspect.Parameter.KEYWORD_ONLY
    nvs = inspect.signature(check_nvs_payload)
    assert list(nvs.parameters) == [
        "envelope",
        "stored",
        "blobs",
        "parent_contents",
        "contract_facts",
    ]
    assert (
        nvs.parameters["contract_facts"].kind is inspect.Parameter.KEYWORD_ONLY
        and nvs.parameters["contract_facts"].default is None
    )


def test_msr_payloads_ignore_contract_facts_and_still_go_to_gate_check_payload() -> (
    None
):
    envelope = {
        "payload_schema": {"id": "msr.calibration", "version": "0.8.0"},
        "payload": {"anything": 1},
        "parents": [],
    }
    assert check_nvs_payload(
        envelope, contract_facts={"not": "even valid"}
    ) == gate.check_payload(envelope)


def test_check_nvs_payload_passes_the_facts_to_the_hidden_trajectory_checker() -> None:
    p = payload_of()
    result = check_nvs_payload(
        envelope_of(p), None, BLOBS, contract_facts=facts_edit("synthetic", True)
    )
    assert isinstance(result, HiddenTrajectoryResult) and [
        v.code for v in result.violations
    ] == ["E_TRAJ_SYNTHETIC"]


def test_all_failures_of_18_are_collected() -> None:
    facts = facts_of(payload_of())
    facts["contract"]["contract_sha256"] = HEX_OTHER
    facts["binding"]["n_gen"] = 9
    facts["positions"][POINT]["dimension"] = 7
    facts["positions"][POINT]["space"]["compute_environment"] = "other"
    facts["origin"]["weights_sha256"] = HEX_OTHER
    facts["synthetic"] = True
    result = run18(facts=facts)
    assert sorted(m.message.split()[0] for m in result.violations) == [
        "18a",
        "18c",
        "18d",
        "18e",
        "18f",
        "contract_facts.synthetic",
    ]


def test_the_catalogue_holds_contract_binding_field_unknown() -> None:
    assert (
        ht.PAYLOAD_SCHEMA_ID,
        "contract_binding.<field>",
        ht.CONTRACT_FIELD_UNKNOWN,
    ) in ht.UNVERIFIABLE_CATALOG


# ----------------------------------------------------------------------------------------------- C14


def _payload_from(point: str, facts: dict[str, Any]) -> dict[str, Any]:
    """An nvs.hidden-trajectory payload for one position of the U4 facts (the U4 names read as U5 names)."""
    pos, binding, origin = facts["positions"][point], facts["binding"], facts["origin"]
    kind = point.partition(":")[0]
    layer = pos["space"]["layer"]
    p: dict[str, Any] = copy.deepcopy(PAYLOADS[MLP])
    p.update(
        point=point,
        kind=kind,
        layer=layer,
        position="final_norm" if kind == "final_norm" else f"L{layer}.{kind}",
        length=pos["stored_range"]["steps"],
        dimension=pos["dimension"],
        row_rule=pos["row_rule"],
        final_norm_applied=pos["final_norm_applied"],
        model_build_id=origin["model_build_id"],
        compute_environment=origin["compute_environment"],
        contract_ref=dict(facts["contract"]),
        unknowns=[],
    )
    p["binding"] = {
        k: binding[k] for k in ("alignment", "n_in", "n_gen", "finish_reason")
    }
    tid = pos["trajectory_id"]
    p["raw_ref"] = {"trajectory_id": tid, "copied": False}
    p["points"].update(
        sha256=tid, uri="blob:sha256:" + tid, shape=[p["length"], p["dimension"]]
    )
    p["token_index"]["shape"] = [p["length"]]
    prov = p["capture_provenance"]
    prov.update(weights_sha256=origin["weights_sha256"])
    for key in (
        "tokenizer_sha256",
        "chat_template_sha256",
        "prompt_ids_sha256",
        "gen_token_ids_sha256",
    ):
        prov[key] = binding[key]
    return p


@pytest.mark.parametrize("point", list(SAMPLE["facts"]["positions"]))
def test_t_u5_c14_the_u4_contract_facts_pass_18a_to_18g(point: str) -> None:
    """Facts made from a real ``build_contract_v2`` contract (nvs-kernel 35f00e7), copied here as a static sample.

    The sample's row rules are the synthetic ones of the U4 tests, so they are put in the registry for this test."""
    facts = SAMPLE["facts"]
    validate_contract_facts(facts)
    p = _payload_from(point, facts)
    kind = p["kind"]
    registry = {p["row_rule"]: {"kind": kind, "alignment": "decides-next/1"}}
    envelope = envelope_of(p, space_id=hid_space_id(facts["positions"][point]["space"]))
    result = check_hidden_trajectory(
        envelope, None, {}, registry=registry, contract_facts=facts
    )
    assert result.violations == (), result.violations
    assert [u.check for u in result.unverifiable] == [
        "token_index_bytes",
        "points_bytes",
    ]


def test_t_u5_c14_a_real_contract_that_is_synthetic_is_refused() -> None:
    facts = copy.deepcopy(SAMPLE["facts"])
    facts["synthetic"] = True
    point = next(iter(facts["positions"]))
    p = _payload_from(point, facts)
    registry = {p["row_rule"]: {"kind": p["kind"], "alignment": "decides-next/1"}}
    result = check_hidden_trajectory(
        envelope_of(p, space_id=hid_space_id(facts["positions"][point]["space"])),
        None,
        {},
        registry=registry,
        contract_facts=facts,
    )
    assert [v.code for v in result.violations] == ["E_TRAJ_SYNTHETIC"]


def test_t_u5_c14_the_sample_is_copied_from_a_clean_checkout_at_35f00e7() -> None:
    assert SAMPLE["source"]["commit"].startswith("35f00e7")
    assert not any(
        name.startswith("nvs") for name in __import__("sys").modules
    )  # nvs-kernel is never imported
