"""contract_facts (nvs.contract-facts/1): the shape check. A wrong shape is raised, never a violation."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest
from contracts.contract_facts import (
    E_GATE_INTERNAL,
    FACTS_VERSION,
    ContractFactsError,
    validate_contract_facts,
)
from contracts.errors import ContractError
from contracts.schemas import CONTRACTS_DIR

SAMPLE = json.loads(
    (CONTRACTS_DIR / "nvs/vectors/contract-facts-from-u4.json").read_text(
        encoding="utf-8"
    )
)
HEX = "a" * 64


def good_facts() -> dict[str, Any]:
    return {
        "facts_version": FACTS_VERSION,
        "contract": {
            "name": "RawObservationContract",
            "version": 2,
            "contract_sha256": HEX,
        },
        "synthetic": False,
        "binding": {
            "alignment": "decides-next/1",
            "n_in": 18,
            "n_gen": 64,
            "finish_reason": "eos",
            "tokenizer_sha256": HEX,
            "chat_template_sha256": "not_applicable",
            "prompt_ids_sha256": HEX,
            "gen_token_ids_sha256": HEX,
        },
        "origin": {
            "model_build_id": "m1",
            "compute_environment": "env",
            "weights_sha256": "unknown",
        },
        "positions": {
            "block_out:15": {
                "trajectory_id": HEX,
                "row_rule": "qwen35-mlx-block-out/1",
                "dimension": 2560,
                "final_norm_applied": True,
                "stored_range": {"steps": 64, "first_row_pos": 17},
                "space": {
                    "model_build_id": "m1",
                    "layer": 15,
                    "row_rule": "qwen35-mlx-block-out/1",
                    "compute_environment": "env",
                    "dimension": 2560,
                    "space_rule": "nvs.hidden-trajectory.space/1",
                },
            }
        },
    }


def edit(path: str, value: Any = ..., *, drop: bool = False) -> dict[str, Any]:
    facts = good_facts()
    cur: Any = facts
    parts = path.split(".")
    for part in parts[:-1]:
        cur = cur[part]
    if drop:
        del cur[parts[-1]]
    else:
        cur[parts[-1]] = value
    return facts


def test_the_design_example_and_the_u4_sample_are_well_formed() -> None:
    validate_contract_facts(good_facts())  # no exception
    validate_contract_facts(SAMPLE["facts"])  # no exception


def test_the_error_is_a_contract_error_with_code_gate_internal_error() -> None:
    assert issubclass(ContractFactsError, ContractError)
    with pytest.raises(ContractFactsError) as info:
        validate_contract_facts({})
    assert info.value.code == E_GATE_INTERNAL == "gate_internal_error"


BAD: dict[str, Callable[[], Any]] = {
    "extra top key": lambda: {**good_facts(), "extra": 1},
    "missing top key": lambda: edit("synthetic", drop=True),
    "not a mapping": list,
    "facts_version other": lambda: edit("facts_version", "nvs.contract-facts/2"),
    "version 3": lambda: edit("contract.version", 3),
    "version 1": lambda: edit("contract.version", 1),
    "version string": lambda: edit("contract.version", "2"),
    "version true": lambda: edit("contract.version", True),
    "version float": lambda: edit("contract.version", 2.0),
    "contract extra key": lambda: edit("contract.extra", 1),
    "contract missing key": lambda: edit("contract.name", drop=True),
    "sha short": lambda: edit("contract.contract_sha256", "a" * 63),
    "sha upper": lambda: edit("contract.contract_sha256", "A" * 64),
    "sha unknown": lambda: edit("contract.contract_sha256", "unknown"),
    "name empty": lambda: edit("contract.name", ""),
    "synthetic not bool": lambda: edit("synthetic", "false"),
    "synthetic int": lambda: edit("synthetic", 0),
    "binding extra key": lambda: edit("binding.extra", 1),
    "binding missing key": lambda: edit("binding.finish_reason", drop=True),
    "n_in zero": lambda: edit("binding.n_in", 0),
    "n_in float": lambda: edit("binding.n_in", 18.0),
    "n_gen bool": lambda: edit("binding.n_gen", True),
    "tokenizer bad": lambda: edit("binding.tokenizer_sha256", "xyz"),
    "tokenizer not_applicable": lambda: edit(
        "binding.tokenizer_sha256", "not_applicable"
    ),
    "chat template bad": lambda: edit("binding.chat_template_sha256", "none"),
    "origin extra key": lambda: edit("origin.extra", 1),
    "origin missing key": lambda: edit("origin.weights_sha256", drop=True),
    "weights not_applicable": lambda: edit("origin.weights_sha256", "not_applicable"),
    "positions empty": lambda: edit("positions", {}),
    "positions list": lambda: edit("positions", []),
    "position extra key": lambda: edit("positions.block_out:15.extra", 1),
    "position missing key": lambda: edit("positions.block_out:15.space", drop=True),
    "trajectory_id bad": lambda: edit("positions.block_out:15.trajectory_id", "zz"),
    "dimension string": lambda: edit("positions.block_out:15.dimension", "2560"),
    "dimension float": lambda: edit("positions.block_out:15.dimension", 2560.0),
    "dimension unknown": lambda: edit("positions.block_out:15.dimension", "unknown"),
    "row_rule unknown-less empty": lambda: edit("positions.block_out:15.row_rule", ""),
    "final_norm_applied string": lambda: edit(
        "positions.block_out:15.final_norm_applied", "true"
    ),
    "stored_range extra": lambda: edit("positions.block_out:15.stored_range.extra", 1),
    "steps negative": lambda: edit("positions.block_out:15.stored_range.steps", -1),
    "steps float": lambda: edit("positions.block_out:15.stored_range.steps", 64.0),
    "first_row_pos bool": lambda: edit(
        "positions.block_out:15.stored_range.first_row_pos", False
    ),
    "space 5 keys": lambda: edit("positions.block_out:15.space.space_rule", drop=True),
    "space 7 keys": lambda: edit("positions.block_out:15.space.kind", "block_out"),
    "layer digit string": lambda: edit("positions.block_out:15.space.layer", "15"),
    "layer float": lambda: edit("positions.block_out:15.space.layer", 15.0),
    "layer bool": lambda: edit("positions.block_out:15.space.layer", True),
    "layer negative": lambda: edit("positions.block_out:15.space.layer", -1),
    "layer other word": lambda: edit("positions.block_out:15.space.layer", "mlp_out"),
    "space dimension float": lambda: edit(
        "positions.block_out:15.space.dimension", 2560.0
    ),
    "space model_build_id empty": lambda: edit(
        "positions.block_out:15.space.model_build_id", ""
    ),
}


@pytest.mark.parametrize("name", list(BAD))
def test_t_u5_c12_a_wrong_shape_is_gate_internal_error(name: str) -> None:
    with pytest.raises(ContractFactsError) as info:
        validate_contract_facts(BAD[name]())
    assert info.value.code == "gate_internal_error"


@pytest.mark.parametrize(
    "path,value",
    [
        ("origin.weights_sha256", "unknown"),
        ("binding.tokenizer_sha256", "unknown"),
        ("binding.chat_template_sha256", "unknown"),
        ("binding.chat_template_sha256", "not_applicable"),
        ("binding.prompt_ids_sha256", "unknown"),
        ("binding.gen_token_ids_sha256", "unknown"),
        ("binding.n_in", "unknown"),
        ("binding.n_gen", "unknown"),
        ("positions.block_out:15.trajectory_id", "unknown"),
        ("positions.block_out:15.final_norm_applied", "unknown"),
        ("positions.block_out:15.stored_range.steps", "unknown"),
        ("positions.block_out:15.stored_range.first_row_pos", "unknown"),
        ("positions.block_out:15.space.layer", "final_norm"),
        ("positions.block_out:15.space.layer", 0),
    ],
)
def test_the_values_the_contract_may_leave_unknown_are_accepted(
    path: str, value: Any
) -> None:
    validate_contract_facts(edit(path, value))  # no exception


def test_validate_does_not_change_its_input() -> None:
    facts = good_facts()
    before = copy.deepcopy(facts)
    validate_contract_facts(facts)
    assert facts == before


def test_the_u4_sample_says_where_it_comes_from() -> None:
    assert SAMPLE["source"]["commit"] == "35f00e749810b7e604b1a48e68e3aa6c88e161eb"
    assert SAMPLE["source"]["branch"] == "feature/contract-v2"
    assert (
        SAMPLE["facts"]["contract"]["version"] == 2
        and SAMPLE["facts"]["synthetic"] is False
    )
