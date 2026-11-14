"""``hid_space``: the ``space_id`` of a hidden-trajectory (design U5 v0.2 section 2, T-U5-SP-01..09)."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pytest
from contracts.errors import ContractError
from contracts.hid_space import (
    E_TRAJ_SPACE_INPUT,
    MATERIAL_KEYS,
    SPACE_RULE,
    SpaceInputError,
    hid_space,
    hid_space_id,
    hid_space_materials,
)
from contracts.jcs import jcs

COMMON: dict[str, Any] = {
    "model_build_id": "qwen35-4b-mlx-4bit",
    "compute_environment": "mlx-4bit",
    "dimension": 2560,
}

#: name -> (layer, row_rule, JCS byte count, space_id). D is not accepted: it only shows the type matters.
SAMPLES: dict[str, tuple[Any, str, int, str]] = {
    "A": (
        15,
        "qwen35-mlx-block-out/1",
        181,
        "hid:1c5f409d15f3dff79b26660b08c57966edab97820a496846956011279a39a0f3",
    ),
    "B": (
        15,
        "qwen35-mlx-mlp-out/1",
        179,
        "hid:501c24c63028d6df5b53c22f8906f7dcd119bfe487cf572dd4e6d022a127cde5",
    ),
    "C": (
        "final_norm",
        "qwen35-mlx-final-norm/1",
        192,
        "hid:5ba5a67a127dfbb73d6532782e62bd1f90631aae6239ede4462376ce161a531c",
    ),
    "D": (
        "15",
        "qwen35-mlx-block-out/1",
        183,
        "hid:373e2b96c624d5bc16a3067acdb24623d0b83e4c818278e25bef4b0a2872d7ff",
    ),
    "E": (
        15,
        "qwen35-mlx-block-out/1+rows0+128/1",
        193,
        "hid:e9b93a52591b9a848190bc0439561a4eb91915970bf7c7cd192758fabe433f90",
    ),
    "F": (
        15,
        "qwen35-mlx-block-out/1+rows128+128/1",
        195,
        "hid:d4dc7ca0c57d63f235ff6382df3fb44246021ec7a1fbd9b4966a8c6078bc356d",
    ),
}
ACCEPTED = ["A", "B", "C", "E", "F"]

A_JCS = (
    b'{"compute_environment":"mlx-4bit","dimension":2560,"layer":15,'
    b'"model_build_id":"qwen35-4b-mlx-4bit","row_rule":"qwen35-mlx-block-out/1",'
    b'"space_rule":"nvs.hidden-trajectory.space/1"}'
)


def materials(name: str) -> dict[str, Any]:
    layer, row_rule, _, _ = SAMPLES[name]
    return {**COMMON, "layer": layer, "row_rule": row_rule, "space_rule": SPACE_RULE}


def args(**override: Any) -> dict[str, Any]:
    return {**COMMON, "layer": 15, "row_rule": "qwen35-mlx-block-out/1", **override}


def direct(material: dict[str, Any]) -> str:
    """The expression of examples/pb_path/ids_cli.py (nvs-runtime), written out here."""
    return "hid:" + hashlib.blake2b(jcs(material), digest_size=32).hexdigest()


def refused(fn: Any, *a: Any, **kw: Any) -> SpaceInputError:
    with pytest.raises(SpaceInputError) as info:
        fn(*a, **kw)
    assert info.value.code == E_TRAJ_SPACE_INPUT == "E_TRAJ_SPACE_INPUT"
    return info.value


# --- SP-01 .. SP-03 ---------------------------------------------------------------------


@pytest.mark.parametrize("name", ACCEPTED)
def test_sp01_samples(name: str) -> None:
    layer, row_rule, size, expected = SAMPLES[name]
    assert hid_space(layer=layer, row_rule=row_rule, **COMMON) == expected
    assert hid_space_id(materials(name)) == expected
    assert len(jcs(materials(name))) == size


def test_sp01_a_jcs_is_the_documented_text() -> None:
    assert jcs(materials("A")) == A_JCS


def test_sp01_window_forms_are_row_rules() -> None:
    for start in (0, 1, 128, 448):
        rule = f"qwen35-mlx-block-out/1+rows{start}+128/1"
        assert hid_space(**args(row_rule=rule)).startswith("hid:")
    assert hid_space(**args(row_rule="qwen35-mlx-block-out/1+rows0+1/12")).startswith(
        "hid:"
    )
    assert hid_space(**args(row_rule="a-b-c-final-norm/10")).startswith("hid:")


def test_sp02_kind_is_told_apart_by_the_row_rule() -> None:
    a, b = SAMPLES["A"], SAMPLES["B"]
    assert a[0] == b[0] == 15
    assert a[3] != b[3]
    assert hid_space(**args()) != hid_space(**args(row_rule="qwen35-mlx-mlp-out/1"))


def test_sp03_layer_type_is_part_of_the_value() -> None:
    layer, row_rule, size, expected = SAMPLES["D"]
    as_string = {
        **COMMON,
        "layer": layer,
        "row_rule": row_rule,
        "space_rule": SPACE_RULE,
    }
    assert len(jcs(as_string)) == size
    assert direct(as_string) == expected  # D, computed by hand
    assert direct(as_string) != SAMPLES["A"][3]
    assert b'"layer":"15"' in jcs(as_string) and b'"layer":15' in jcs(materials("A"))
    refused(hid_space, layer="15", row_rule=row_rule, **COMMON)
    refused(hid_space_id, as_string)  # D is not accepted by hid_space_id either


# --- SP-04 ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("layer", True),
        ("layer", False),
        ("layer", 1.0),
        ("layer", -1),
        ("layer", 2**53),
        ("layer", "mlp_out"),
        ("layer", "block_out"),
        ("layer", "Final_norm"),
        ("layer", "final_norm\n"),
        ("layer", ""),
        ("layer", "15"),
        ("layer", None),
        ("layer", [15]),
        ("dimension", 0),
        ("dimension", 65536),
        ("dimension", -1),
        ("dimension", True),
        ("dimension", 2560.0),
        ("dimension", "2560"),
        ("dimension", None),
        ("model_build_id", ""),
        ("model_build_id", "has space"),
        ("model_build_id", "x" * 257),
        ("model_build_id", "name\n"),
        ("model_build_id", "name\u00e9"),
        ("model_build_id", b"name"),
        ("model_build_id", None),
        ("model_build_id", 5),
        ("compute_environment", ""),
        ("compute_environment", "has space"),
        ("compute_environment", "x" * 257),
        ("compute_environment", "mlx-4bit\n"),
        ("compute_environment", None),
        ("row_rule", ""),
        ("row_rule", "MLX block output of the model"),
        ("row_rule", "qwen35-mlx-block-out"),
        ("row_rule", "qwen35-mlx-block-out/0"),
        ("row_rule", "qwen35-mlx-block-out/01"),
        ("row_rule", "qwen35-mlx-block-out/1\n"),
        ("row_rule", "qwen35-mlx-attention/1"),
        ("row_rule", "qwen35-mlx-block_out/1"),
        ("row_rule", "Qwen35-mlx-block-out/1"),
        ("row_rule", "block-out/1"),
        ("row_rule", "qwen35-mlx-block-out/1+rows01+128/1"),
        ("row_rule", "qwen35-mlx-block-out/1+rows0+0/1"),
        ("row_rule", "qwen35-mlx-block-out/1+rows0+128/0"),
        ("row_rule", "qwen35-mlx-block-out/1+rows-1+128/1"),
        ("row_rule", "qwen35-mlx-block-out/1+rows0+128"),
        ("row_rule", "qwen35-mlx-block-out/1+rows0+128/1+rows0+128/1"),
        ("row_rule", "qwen35-mlx-block-out/1+rows0+128/1\n"),
        ("row_rule", None),
        ("row_rule", 1),
    ],
)
def test_sp04_refused_inputs(field: str, value: Any) -> None:
    refused(hid_space, **args(**{field: value}))
    refused(hid_space_materials, **args(**{field: value}))
    refused(hid_space_id, {**materials("A"), field: value})


def test_sp04_limits_are_accepted() -> None:
    for layer in (0, 1, 2**53 - 1, "final_norm"):
        hid_space(**args(layer=layer))
    for dimension in (1, 65535):
        hid_space(**args(dimension=dimension))
    hid_space(**args(model_build_id="x" * 256, compute_environment="A._:/+@=-9"))


def test_sp04_messages_name_the_field() -> None:
    assert "layer" in str(refused(hid_space, **args(layer="15")))
    assert "dimension" in str(refused(hid_space, **args(dimension=0)))
    assert "row_rule" in str(refused(hid_space, **args(row_rule="")))
    assert "model_build_id" in str(refused(hid_space, **args(model_build_id="")))


def test_space_input_error_is_a_contract_error() -> None:
    error = refused(hid_space, **args(dimension=0))
    assert (
        isinstance(error, ContractError)
        and error.code == "E_TRAJ_SPACE_INPUT"
        and error.message
    )


# --- SP-05 .. SP-08 -----------------------------------------------------------------------


@pytest.mark.parametrize("extra", ["kind", "point", "binding"])
def test_sp05_extra_keys_are_refused(extra: str) -> None:
    refused(hid_space_id, {**materials("A"), extra: "block_out"})
    refused(hid_space_id, {**materials("A"), 7: "x"})


@pytest.mark.parametrize("missing", MATERIAL_KEYS)
def test_sp06_missing_key_is_refused(missing: str) -> None:
    broken = materials("A")
    del broken[missing]
    refused(hid_space_id, broken)


def test_sp06_not_a_mapping_is_refused() -> None:
    refused(hid_space_id, [("layer", 15)])
    refused(hid_space_id, None)


@pytest.mark.parametrize("name", ACCEPTED)
def test_sp07_form(name: str) -> None:
    value = hid_space_id(materials(name))
    assert len(value) == 68 and re.fullmatch(r"hid:[0-9a-f]{64}", value)


@pytest.mark.parametrize(
    "rule",
    ["nvs.hidden-trajectory.space/2", "nvs.hidden-trajectory.space/1 ", "", None, 1],
)
def test_sp08_only_space_rule_1_is_accepted(rule: Any) -> None:
    refused(hid_space_id, {**materials("A"), "space_rule": rule})


def test_hid_space_materials_returns_the_six_keys() -> None:
    result = hid_space_materials(**args())
    assert set(result) == set(MATERIAL_KEYS) and result["space_rule"] == SPACE_RULE
    assert result == materials("A")
    assert hid_space_id(result) == SAMPLES["A"][3]
    assert (
        hid_space_id(dict(reversed(list(result.items())))) == SAMPLES["A"][3]
    )  # key order does not matter


# --- SP-09 ---------------------------------------------------------------------------------


EXTRA_CASES = [
    {
        "model_build_id": "llama31-8b-mlx-4bit",
        "layer": 0,
        "row_rule": "llama31-mlx-final-norm/1",
        "dimension": 4096,
    },
    {
        "model_build_id": "m",
        "layer": 31,
        "row_rule": "a-b-mlp-out/12",
        "dimension": 1,
        "compute_environment": "e",
    },
    {
        "model_build_id": "x" * 256,
        "layer": 2**53 - 1,
        "row_rule": "a-b-block-out/1+rows7+3/2",
        "dimension": 65535,
    },
    {
        "model_build_id": "m:1/2+3@4=5._-",
        "layer": "final_norm",
        "row_rule": "a-b-final-norm/1",
        "dimension": 16,
    },
]


@pytest.mark.parametrize("name", ACCEPTED)
def test_sp09_matches_the_ids_cli_expression_on_the_samples(name: str) -> None:
    layer, row_rule, _, _ = SAMPLES[name]
    assert hid_space(layer=layer, row_rule=row_rule, **COMMON) == direct(
        materials(name)
    )


@pytest.mark.parametrize("case", EXTRA_CASES)
def test_sp09_matches_the_ids_cli_expression_on_more_inputs(
    case: dict[str, Any],
) -> None:
    full = {"compute_environment": "mlx-4bit", **case}
    expected = direct({**full, "space_rule": "nvs.hidden-trajectory.space/1"})
    assert hid_space(**full) == expected
