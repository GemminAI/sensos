"""The Observation Interface (U1) without a model or MLX.

Fake engines and a fake tokenizer drive the two existing capture providers; their results are the
input of the conversions. Test ids (``T-XX-nn``) are those of the U1 design; one test per id.

Decisions left to the implementation, fixed here:

* a big-endian float32 state is reported as ``OBS_STATE_LAYOUT`` (it is a float32, in the wrong byte
  order); every other non-float32 dtype is ``OBS_STATE_DTYPE`` (``test_t_vc_12``);
* ``ObservationIssue.message`` is a short English sentence; the tests compare ``code`` and ``path`` only.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import pytest

import sensos_inference
from sensos_inference import observation
from sensos_inference.observation import (
    ALIGNMENT_DECIDES_NEXT,
    DELIVERIES,
    EQUIVALENCE_CHECKS,
    FINISH_REASONS,
    KINDS,
    RESERVED_KINDS,
    ROW_RULES,
    SPACE_RULE,
    TOKEN_SCOPES,
    UNKNOWN,
    CaptureCapabilities,
    CaptureProvenance,
    CaptureRequest,
    ObservationCapture,
    ObservationError,
    ObservationIssue,
    ObservationPoint,
    RowRuleSpec,
    ensure_valid,
    from_llama31,
    from_qwen35,
    llama31_mlx_capabilities,
    point_from_legacy_name,
    point_from_name,
    qwen35_mlx_capabilities,
    row_positions,
    space_collisions,
    space_materials,
    validate_capabilities,
    validate_capture,
    validate_request,
)
from sensos_inference.providers import llama31_mlx_capture, qwen35_mlx_capture
from sensos_inference.providers.llama31_mlx_capture import Llama31MLXCaptureProvider, input_ids_sha256
from sensos_inference.providers.qwen35_mlx_capture import (
    PILOT_POSITIONS,
    CapturePosition,
    Qwen35MLXCaptureProvider,
)

VOCAB = 40
EOS = 39
EOS2 = 38
PROMPT = [100, 5, 6, 101]
LLAMA_DIM = 4096
QWEN_DIM = 6
MSG = [{"role": "user", "content": "x"}]
LLAMA_BUILD = "llama31-8b-instruct-mlx-4bit"
QWEN_BUILD = "qwen35-0.8b-orig"


# ---- fake engines and tokenizers (as in the existing provider tests) ------------------------------


def _one_hot(token: int) -> np.ndarray:
    """Log-probabilities that make any sampler of the providers choose ``token``."""
    scores = np.full(VOCAB, -1e30)
    scores[token] = 0.0
    return scores


def _llama_state(token: int, position: int) -> np.ndarray:
    return np.full(LLAMA_DIM, token * 1000.0 + position, dtype=np.float32)


def _qwen_state(token: int, position: int, salt: float) -> np.ndarray:
    return np.full(QWEN_DIM, token * 1000.0 + position + salt, dtype=np.float32)


class _ScriptedEngine:
    """Decides ``script[k]`` in step k (token 1 after the script). States depend on token and position."""

    state_dtype = "bfloat16"

    def __init__(self, script: list[int], positions: Any = None) -> None:
        self.script, self.positions = script, positions
        self.calls = 0
        self.position = 0

    def prefill(self, ids: Any) -> None:
        self.position = len(ids)

    def step(self, token: int) -> tuple[np.ndarray, Any]:
        chosen = self.script[self.calls] if self.calls < len(self.script) else 1
        self.calls += 1
        if self.positions is None:
            state: Any = _llama_state(token, self.position)
        else:
            state = {p.name: _qwen_state(token, self.position, 0.25 * i) for i, p in enumerate(self.positions)}
        self.position += 1
        return _one_hot(chosen), state


class _Tok:
    chat_template = "{{ messages }}"
    eos_token_ids = {EOS}  # noqa: RUF012
    all_special_ids = [100]  # noqa: RUF012
    added_tokens_decoder: dict = {}  # noqa: RUF012

    def apply_chat_template(self, messages: Any, add_generation_prompt: bool, tokenize: bool, **kwargs: Any) -> list[int]:
        return list(PROMPT)

    def decode(self, ids: Any) -> str:
        return " ".join(str(i) for i in ids)


class _QwenArgs:
    hidden_size = QWEN_DIM


class _QwenLM:
    args = _QwenArgs()


class _QwenModel:
    language_model = _QwenLM()

    class args:  # noqa: N801
        text_config = {"eos_token_id": EOS2, "hidden_size": QWEN_DIM}  # noqa: RUF012


def _snapshot(tmp_path: Path) -> Path:
    snap = tmp_path / "snap"
    snap.mkdir(exist_ok=True)
    (snap / "tokenizer.json").write_text("{}")
    (snap / "model.safetensors").write_bytes(b"w")
    return snap


def _llama_result(tmp_path: Path, script: list[int], *, max_tokens: int = 64, revision: str | None = None) -> Any:
    provider = Llama31MLXCaptureProvider(
        "local/model",
        revision=revision,
        loader=lambda _t: (object(), _Tok()),
        engine_factory=lambda _m: _ScriptedEngine(script),
        snapshot_dir=_snapshot(tmp_path),
        hash_cache_dir=tmp_path / "hashes",
    )
    return provider.capture_chat(MSG, max_tokens=max_tokens, seed=1)


def _qwen_result(
    tmp_path: Path, script: list[int], *, max_tokens: int = 64, positions: Any = PILOT_POSITIONS
) -> Any:
    provider = Qwen35MLXCaptureProvider(
        "local/qwen",
        loader=lambda _t: (_QwenModel(), _Tok()),
        engine_factory=lambda _m, pos: _ScriptedEngine(script, pos),
        snapshot_dir=_snapshot(tmp_path),
        hash_cache_dir=tmp_path / "hashes",
    )
    return provider.capture_chat(MSG, max_tokens=max_tokens, seed=1, positions=positions)


def _llama_capture(tmp_path: Path) -> ObservationCapture:
    result = _llama_result(tmp_path, [7, 8, 9, EOS])
    assert result.finish_reason == "eos"
    return from_llama31(result, model_build_id=LLAMA_BUILD, compute_environment="mlx-4bit")


def _qwen_capture(tmp_path: Path) -> ObservationCapture:
    result = _qwen_result(tmp_path, [7, 8, 9, EOS])
    assert result.finish_reason == "eos"
    return from_qwen35(result, model_build_id=QWEN_BUILD, compute_environment="mlx-bf16-metal")


# ---- hand-made captures (F-H) --------------------------------------------------------------------


def _sha(ids: Any) -> str:
    return hashlib.sha256(np.asarray(list(ids), dtype="<i8").tobytes()).hexdigest()


def _prov(n_gen: int = 3, **overrides: Any) -> CaptureProvenance:
    values: dict[str, Any] = {
        "model_ref": "local/qwen",
        "revision": "a" * 40,
        "weights_sha256": "b" * 64,
        "tokenizer_sha256": "c" * 64,
        "chat_template_sha256": "d" * 64,
        "special_tokens_in": ((0, 100), (3, 101)),
        "prompt_ids_sha256": _sha(PROMPT),
        "gen_token_ids_sha256": _sha(range(7, 7 + n_gen)),
        "runtime": {"backend": "mlx", "mlx": "0.1", "mlx_lm": "0.2", "device": "gpu"},
        "sampler": {"seed": 0},
        "max_tokens": 64,
        "eos_ids": (EOS2, EOS),
    }
    values.update(overrides)
    return CaptureProvenance(**values)


def _capture(n_gen: int = 3, **overrides: Any) -> ObservationCapture:
    """A valid capture: D=4, n_in=4, points ``block_out:1`` and ``final_norm`` (qwen35 adapter)."""
    dim = 4
    points = ("block_out:1", "final_norm")
    row_pos, row_decides = row_positions(len(PROMPT), n_gen)
    values: dict[str, Any] = {
        "adapter": "qwen35-mlx-capture",
        "model_build_id": QWEN_BUILD,
        "compute_environment": "mlx-bf16-metal",
        "dimension": dim,
        "prompt_ids": np.array(PROMPT, dtype=np.int64),
        "token_ids": np.arange(7, 7 + n_gen, dtype=np.int64),
        "finish_reason": "eos",
        "points": points,
        "states": {p: np.arange(n_gen * dim, dtype=np.float32).reshape(n_gen, dim) for p in points},
        "row_rule": {"block_out:1": "qwen35-mlx-block-out/1", "final_norm": "qwen35-mlx-final-norm/1"},
        "row_pos": {p: row_pos.copy() for p in points},
        "row_decides": {p: row_decides.copy() for p in points},
        "final_norm_applied": {"block_out:1": False, "final_norm": True},
        "state_dtype": "bfloat16",
        "provenance": _prov(n_gen),
        "unknowns": (),
    }
    values.update(overrides)
    return ObservationCapture(**values)


def _with(mapping: Mapping[str, Any], key: str, value: Any) -> dict[str, Any]:
    return {**mapping, key: value}


def _without(mapping: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in mapping.items() if k != key}


def _codes(issues: list[ObservationIssue]) -> list[str]:
    return [i.code for i in issues]


def _raised(call: Any, *args: Any, **kwargs: Any) -> list[str]:
    with pytest.raises(ObservationError) as info:
        call(*args, **kwargs)
    return [i.code for i in info.value.issues]


def _qwen_caps(**overrides: Any) -> CaptureCapabilities:
    return dataclasses.replace(qwen35_mlx_capabilities(n_layers=2, dimension=6, native_dtype="bfloat16"), **overrides)


def _llama_caps(**overrides: Any) -> CaptureCapabilities:
    return dataclasses.replace(llama31_mlx_capabilities(native_dtype="bfloat16"), **overrides)


# ---- 7.1 points and rows -------------------------------------------------------------------------


def test_t_pt_01_point_names() -> None:
    cases = [
        (ObservationPoint("block_out", 16), "block_out:16", "L16.block_out", 16),
        (ObservationPoint("mlp_out", 15), "mlp_out:15", "L15.mlp_out", 15),
        (ObservationPoint("final_norm"), "final_norm", "final_norm", "final_norm"),
    ]
    for point, name, legacy, label in cases:
        assert (point.name, point.legacy_name, point.layer_label) == (name, legacy, label)
    assert ObservationPoint("block_out", 16).kind_slug == "block-out"
    assert type(ObservationPoint("mlp_out", 15).layer_label) is int


def test_t_pt_02_invalid_points() -> None:
    bad = [("bogus", 1), ("mlp_out", None), ("mlp_out", -1), ("mlp_out", True), ("final_norm", 3)]
    assert [_raised(ObservationPoint, *args) for args in bad] == [
        ["OBS_POINT_KIND"],
        ["OBS_POINT_LAYER"],
        ["OBS_POINT_LAYER"],
        ["OBS_POINT_LAYER"],
        ["OBS_POINT_LAYER"],
    ]
    assert issubclass(ObservationError, ValueError)


def test_t_pt_03_reserved_kinds() -> None:
    for args in (("embed",), ("attn_out", 3), ("logit_summary",)):
        assert _raised(ObservationPoint, *args) == ["OBS_POINT_KIND_RESERVED"]
    assert set(RESERVED_KINDS) & set(KINDS) == set()


def test_t_pt_04_point_name_round_trip() -> None:
    for name in ("block_out:0", "final_norm", "mlp_out:15"):
        assert point_from_name(name).name == name
    assert point_from_name("block_out:0") == ObservationPoint("block_out", 0)


def test_t_pt_05_invalid_point_names() -> None:
    for name in ("block_out:016", "block_out:-1", "L15.mlp_out", " block_out:1", "final_norm:0", ""):
        assert _raised(point_from_name, name) == ["OBS_POINT_NAME"], name
    assert _raised(point_from_name, "attn_out:3") == ["OBS_POINT_KIND_RESERVED"]
    assert _raised(point_from_name, "embed") == ["OBS_POINT_KIND_RESERVED"]
    assert _raised(point_from_name, 5) == ["OBS_POINT_NAME"]  # type: ignore[arg-type]


def test_t_pt_06_legacy_names() -> None:
    assert point_from_legacy_name("L15.mlp_out") == ObservationPoint("mlp_out", 15)
    assert point_from_legacy_name("final_norm") == ObservationPoint("final_norm")
    assert _raised(point_from_legacy_name, "mlp_out:15") == ["OBS_POINT_NAME"]
    assert _raised(point_from_legacy_name, "L015.mlp_out") == ["OBS_POINT_NAME"]


def test_t_pt_07_pilot_positions_agree_with_the_existing_code() -> None:
    assert len(PILOT_POSITIONS) == 5
    for position in PILOT_POSITIONS:
        point = point_from_legacy_name(position.name)
        assert (point.kind, point.layer, point.layer_label) == (position.kind, position.layer, position.layer_label)
        assert point.legacy_name == position.name


def test_t_rp_01_rows_of_eos_and_length_endings() -> None:
    row_pos, row_decides = row_positions(4, 3)
    assert row_pos.tolist() == [3, 4, 5] and row_decides.tolist() == [0, 1, 2]
    assert row_pos.dtype == np.int64 and row_decides.dtype == np.int64
    assert not row_pos.flags.writeable and not row_decides.flags.writeable


def test_t_rp_02_one_token() -> None:
    row_pos, row_decides = row_positions(4, 1)
    assert row_pos.tolist() == [3] and row_decides.tolist() == [0]


def test_t_rp_03_no_token() -> None:
    row_pos, row_decides = row_positions(4, 0)
    assert row_pos.shape == (0,) and row_decides.shape == (0,)
    assert row_pos.dtype == np.int64 and row_decides.dtype == np.int64


def test_t_rp_04_one_prompt_token() -> None:
    row_pos, row_decides = row_positions(1, 2)
    assert row_pos.tolist() == [0, 1] and row_decides.tolist() == [0, 1]


def test_t_rp_05_argument_checks() -> None:
    for args in ((0, 1), (4, -1), (True, 1), (4.0, 1)):
        assert _raised(row_positions, *args) == ["OBS_ROW_ARG"], args


# ---- 7.2 registry and space ----------------------------------------------------------------------


def test_t_rr_01_registry() -> None:
    assert set(ROW_RULES) == {
        "llama31-mlx-final-norm/1",
        "qwen35-mlx-mlp-out/1",
        "qwen35-mlx-block-out/1",
        "qwen35-mlx-final-norm/1",
    }
    with pytest.raises(TypeError):
        ROW_RULES["x"] = ROW_RULES["qwen35-mlx-mlp-out/1"]  # type: ignore[index]
    assert all(isinstance(spec, RowRuleSpec) and spec.name == key for key, spec in ROW_RULES.items())


def test_t_rr_02_names_carry_their_kind() -> None:
    for name, spec in ROW_RULES.items():
        assert observation._ROW_RULE_NAME.fullmatch(name), name
        slug = observation._ROW_RULE_NAME.fullmatch(name).group(1)  # type: ignore[union-attr]
        assert slug == spec.kind.replace("_", "-")
        assert name.split("/")[0].endswith("-" + slug)
        assert spec.alignment == ALIGNMENT_DECIDES_NEXT
    assert observation._ROW_RULE_NAME.fullmatch("qwen35-mlx-mlp-out/0") is None
    assert observation._ROW_RULE_NAME.fullmatch("qwen35-mlx-hidden/1") is None


def test_t_rr_03_registry_agrees_with_the_providers() -> None:
    for kind, name in qwen35_mlx_capture.ROW_RULES.items():
        assert ROW_RULES[name].kind == kind
        assert ROW_RULES[name].source_text == qwen35_mlx_capture.ROW_RULE_TEXT
        assert ROW_RULES[name].adapter == Qwen35MLXCaptureProvider.name
    llama = ROW_RULES["llama31-mlx-final-norm/1"]
    assert llama.source_text == llama31_mlx_capture.ROW_RULE
    assert llama.adapter == Llama31MLXCaptureProvider.name and llama.kind == "final_norm"
    assert set(KINDS) == set(qwen35_mlx_capture.KINDS)
    assert llama31_mlx_capabilities().dimension == llama31_mlx_capture.HIDDEN_DIMENSION


def test_t_sp_01_kinds_differ_in_the_materials(tmp_path: Path) -> None:
    capture = _qwen_capture(tmp_path)
    mlp, block = space_materials(capture, "mlp_out:15"), space_materials(capture, "block_out:15")
    assert mlp["layer"] == 15 and block["layer"] == 15 and type(mlp["layer"]) is int
    assert mlp["row_rule"] != block["row_rule"]
    expected_keys = {"model_build_id", "layer", "row_rule", "compute_environment", "dimension", "space_rule"}
    assert set(mlp) == expected_keys and set(block) == expected_keys
    assert mlp["dimension"] == QWEN_DIM and mlp["model_build_id"] == QWEN_BUILD
    assert space_collisions(capture) == []


def test_t_sp_02_final_norm_layer_is_a_string(tmp_path: Path) -> None:
    materials = space_materials(_qwen_capture(tmp_path), "final_norm")
    assert materials["layer"] == "final_norm" and materials["space_rule"] == SPACE_RULE
    assert SPACE_RULE == "nvs.hidden-trajectory.space/1"


def test_t_sp_03_collision_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = {"qwen35-mlx-mlp-out/1": ROW_RULES["qwen35-mlx-mlp-out/1"], "qwen35-mlx-final-norm/1": ROW_RULES["qwen35-mlx-final-norm/1"]}
    monkeypatch.setattr(observation, "ROW_RULES", MappingProxyType(broken))
    same = "qwen35-mlx-mlp-out/1"
    capture = _capture(
        points=("mlp_out:1", "block_out:1", "final_norm"),
        states={p: np.zeros((3, 4), np.float32) for p in ("mlp_out:1", "block_out:1", "final_norm")},
        row_rule={"mlp_out:1": same, "block_out:1": same, "final_norm": "qwen35-mlx-final-norm/1"},
        row_pos={p: row_positions(4, 3)[0] for p in ("mlp_out:1", "block_out:1", "final_norm")},
        row_decides={p: row_positions(4, 3)[1] for p in ("mlp_out:1", "block_out:1", "final_norm")},
        final_norm_applied={"mlp_out:1": False, "block_out:1": False, "final_norm": True},
    )
    codes = _codes(validate_capture(capture))
    assert "OBS_SPACE_COLLISION" in codes and "OBS_ROW_RULE_KIND" in codes
    assert space_collisions(capture) == [("mlp_out:1", "block_out:1")]


def test_t_sp_04_unknown_point() -> None:
    assert _raised(space_materials, _capture(), "block_out:99") == ["OBS_POINT_NAME"]
    assert _raised(space_materials, _capture(), "L1.block_out") == ["OBS_POINT_NAME"]


# ---- 7.3 capabilities and requests ---------------------------------------------------------------


def test_t_cap_01_llama_capabilities() -> None:
    caps = llama31_mlx_capabilities()
    assert validate_capabilities(caps) == []
    assert caps.points == ("final_norm",) and caps.dimension == 4096
    assert caps.equivalence_check == "bit" and caps.unknowns == ("native_dtype",)
    assert caps.row_rule == {"final_norm": "llama31-mlx-final-norm/1"}
    assert caps.final_norm_applied == {"final_norm": True} and caps.delivery == "per-request"
    assert caps.token_scope == TOKEN_SCOPES == ("gen",)


def test_t_cap_02_known_dtype_leaves_no_unknown() -> None:
    caps = llama31_mlx_capabilities(native_dtype="float16")
    assert validate_capabilities(caps) == [] and caps.unknowns == ()


def test_t_cap_03_qwen_capabilities() -> None:
    caps = qwen35_mlx_capabilities(n_layers=24, dimension=1024)
    assert validate_capabilities(caps) == []
    assert len(caps.points) == 49 == 24 + 24 + 1
    assert caps.points[:2] == ("block_out:0", "block_out:1") and caps.points[23] == "block_out:23"
    assert caps.points[24] == "mlp_out:0" and caps.points[47] == "mlp_out:23" and caps.points[-1] == "final_norm"
    assert [p for p, v in caps.final_norm_applied.items() if v is True] == ["final_norm"]
    assert caps.equivalence_check == "bit" and caps.dimension == 1024 and caps.unknowns == ("native_dtype",)
    assert caps.row_rule["mlp_out:3"] == "qwen35-mlx-mlp-out/1"


def test_t_cap_04_n_layers_argument() -> None:
    for n_layers in (0, True, -1, 2.0):
        assert _raised(qwen35_mlx_capabilities, n_layers=n_layers, dimension=6) == ["OBS_CAP_ARG"], n_layers


def test_t_cap_05_basic_fields() -> None:
    cases: list[tuple[dict[str, Any], list[str]]] = [
        ({"adapter": ""}, ["OBS_TEXT", "OBS_ROW_RULE_ADAPTER"]),
        ({"runtime": "mlx lm"}, ["OBS_TEXT"]),
        ({"native_dtype": "a b"}, ["OBS_TEXT"]),
        ({"dimension": 0}, ["OBS_DIM_RANGE"]),
        ({"dimension": True}, ["OBS_DIM_RANGE"]),
        ({"dimension": 2**53}, ["OBS_DIM_RANGE"]),
        ({"points": ()}, ["OBS_POINTS_EMPTY"]),
        ({"points": ("L1.block_out",)}, ["OBS_POINT_NAME"]),
        ({"points": ("final_norm", "final_norm")}, ["OBS_POINT_DUP"]),
    ]
    for override, expected in cases:
        assert _codes(validate_capabilities(_llama_caps(**override))) == expected, override
    assert validate_capabilities(_llama_caps(dimension=2**53 - 1)) == []
    assert _codes(validate_capabilities("x")) == ["OBS_TYPE"]


def test_t_cap_06_row_rule() -> None:
    qwen = _qwen_caps()
    cases = [
        (qwen, _without(qwen.row_rule, "final_norm"), ["OBS_KEYS"]),
        (qwen, _with(qwen.row_rule, "block_out:9", "qwen35-mlx-block-out/1"), ["OBS_KEYS"]),
        (qwen, _with(qwen.row_rule, "mlp_out:0", "qwen35-mlx-zzz-out/1"), ["OBS_ROW_RULE_UNKNOWN"]),
        (qwen, _with(qwen.row_rule, "final_norm", "qwen35-mlx-mlp-out/1"), ["OBS_ROW_RULE_KIND"]),
        (_llama_caps(), {"final_norm": "qwen35-mlx-final-norm/1"}, ["OBS_ROW_RULE_ADAPTER"]),
    ]
    for caps, row_rule, expected in cases:
        assert _codes(validate_capabilities(dataclasses.replace(caps, row_rule=row_rule))) == expected
    bad = dataclasses.replace(qwen, row_rule=_with(qwen.row_rule, "mlp_out:0", "qwen35-mlx-zzz-out/1"))
    assert validate_capabilities(bad)[0].path == "row_rule.mlp_out:0"


def test_t_cap_07_final_norm_applied_shape_and_type() -> None:
    llama = _llama_caps()
    cases = [
        (True, ["OBS_FNA_TYPE"]),
        ({}, ["OBS_KEYS"]),
        ({"final_norm": True, "block_out:1": False}, ["OBS_KEYS"]),
        ({"final_norm": 1}, ["OBS_FNA_TYPE"]),
        ({"final_norm": None}, ["OBS_FNA_TYPE"]),
        ({"final_norm": "true"}, ["OBS_FNA_TYPE"]),
    ]
    for value, expected in cases:
        assert _codes(validate_capabilities(dataclasses.replace(llama, final_norm_applied=value))) == expected, value


def test_t_cap_08_final_norm_applied_definition() -> None:
    llama, qwen = _llama_caps(), _qwen_caps()
    for value in (False, UNKNOWN):
        unknowns = ("final_norm_applied.final_norm",) if value == UNKNOWN else ()
        caps = dataclasses.replace(llama, final_norm_applied={"final_norm": value}, unknowns=unknowns)
        assert _codes(validate_capabilities(caps)) == ["OBS_FNA_DEFINITION"], value
    for value in (True, UNKNOWN):
        unknowns = ("final_norm_applied.mlp_out:1",) if value == UNKNOWN else ()
        caps = dataclasses.replace(qwen, final_norm_applied=_with(qwen.final_norm_applied, "mlp_out:1", value), unknowns=unknowns)
        assert _codes(validate_capabilities(caps)) == ["OBS_FNA_DEFINITION"], value


def test_t_cap_09_unknown_block_out_must_be_listed() -> None:
    qwen = _qwen_caps()
    fna = _with(qwen.final_norm_applied, "block_out:1", UNKNOWN)
    listed = dataclasses.replace(qwen, final_norm_applied=fna, unknowns=("final_norm_applied.block_out:1",))
    assert validate_capabilities(listed) == []
    not_listed = dataclasses.replace(qwen, final_norm_applied=fna)
    assert _codes(validate_capabilities(not_listed)) == ["OBS_UNKNOWNS"]


def test_t_cap_10_value_per_point() -> None:
    caps = qwen35_mlx_capabilities(n_layers=3, dimension=6, native_dtype="bfloat16")
    mixed = dataclasses.replace(caps, final_norm_applied=_with(caps.final_norm_applied, "block_out:2", True))
    assert mixed.final_norm_applied["block_out:1"] is False and mixed.final_norm_applied["block_out:2"] is True
    assert validate_capabilities(mixed) == []


def test_t_cap_11_scope_delivery_equivalence_unknowns() -> None:
    llama = _llama_caps()
    assert _codes(validate_capabilities(dataclasses.replace(llama, token_scope=("input", "gen")))) == ["OBS_SCOPE"]
    assert _codes(validate_capabilities(dataclasses.replace(llama, delivery="stream"))) == ["OBS_DELIVERY"]
    assert _codes(validate_capabilities(dataclasses.replace(llama, equivalence_check="exact"))) == ["OBS_EQUIV"]
    qwen = _qwen_caps(native_dtype=UNKNOWN)
    fna = _with(qwen.final_norm_applied, "block_out:0", UNKNOWN)
    ascending = ("final_norm_applied.block_out:0", "native_dtype")
    assert validate_capabilities(dataclasses.replace(qwen, final_norm_applied=fna, unknowns=ascending)) == []
    reverse = dataclasses.replace(qwen, final_norm_applied=fna, unknowns=ascending[::-1])
    assert _codes(validate_capabilities(reverse)) == ["OBS_UNKNOWNS"]
    assert set(DELIVERIES) == {"per-request", "per-token"} and set(EQUIVALENCE_CHECKS) == {"bit", "numeric", "none"}


def test_t_cap_12_all_issues_are_returned() -> None:
    caps = _llama_caps(runtime="", dimension=0, delivery="stream")
    assert _codes(validate_capabilities(caps)) == ["OBS_TEXT", "OBS_DIM_RANGE", "OBS_DELIVERY"]


def test_t_cap_13_another_runtime_fits_without_changing_types(monkeypatch: pytest.MonkeyPatch) -> None:
    rule = RowRuleSpec("x-vllm-block-out/1", "block_out", "x-vllm", ALIGNMENT_DECIDES_NEXT, "text")
    points = ("block_out:0", "block_out:1", "block_out:2")
    caps = CaptureCapabilities(
        adapter="x-vllm",
        runtime="vllm",
        dimension=8,
        points=points,
        row_rule={p: rule.name for p in points},
        final_norm_applied={p: False for p in points},
        delivery="per-request",
        native_dtype="bfloat16",
        equivalence_check="numeric",
    )
    assert "x-vllm-block-out/1" not in ROW_RULES
    assert _codes(validate_capabilities(caps)) == ["OBS_ROW_RULE_UNKNOWN"] * 3
    monkeypatch.setattr(observation, "ROW_RULES", MappingProxyType({**ROW_RULES, rule.name: rule}))
    assert validate_capabilities(caps) == []


def test_t_req_01_valid_request() -> None:
    caps = _qwen_caps()
    request = CaptureRequest(points=("block_out:1", "final_norm"), max_tokens=8)
    assert validate_request(request, caps) == []
    assert request.token_scope == "gen" and request.logit_summary is None and request.sampling == {}


def test_t_req_02_points_of_a_request() -> None:
    caps = _qwen_caps()
    cases = [
        (("block_out:7",), ["OBS_REQ_POINT_UNDECLARED"]),
        (("attn_out:3",), ["OBS_POINT_KIND_RESERVED"]),
        ((), ["OBS_POINTS_EMPTY"]),
        (("final_norm", "final_norm"), ["OBS_POINT_DUP"]),
        (("L1.block_out",), ["OBS_POINT_NAME"]),
    ]
    for points, expected in cases:
        assert _codes(validate_request(CaptureRequest(points=points, max_tokens=8), caps)) == expected, points


def test_t_req_03_other_fields_of_a_request() -> None:
    caps = _qwen_caps()

    def run(**kw: Any) -> list[str]:
        return _codes(validate_request(CaptureRequest(points=("final_norm",), **{"max_tokens": 8, **kw}), caps))

    assert run(max_tokens=0) == ["OBS_REQ_MAX_TOKENS"] and run(max_tokens=True) == ["OBS_REQ_MAX_TOKENS"]
    assert run(token_scope="input") == ["OBS_REQ_SCOPE"]
    assert run(logit_summary={"top_k": 5}) == ["OBS_REQ_UNSUPPORTED"]
    assert run(sampling=[]) == ["OBS_TYPE"]
    assert run(sampling={"seed": 3}) == []
    assert _codes(validate_request("x", caps)) == ["OBS_TYPE"]  # type: ignore[arg-type]


def test_t_req_04_invalid_capabilities() -> None:
    bad = _llama_caps(runtime="")
    request = CaptureRequest(points=("final_norm",), max_tokens=8)
    assert _codes(validate_request(request, bad)) == ["OBS_CAP_INVALID"]


# ---- 7.4 checks of a capture ---------------------------------------------------------------------


def test_t_vc_01_valid_capture() -> None:
    assert validate_capture(_capture()) == []


def test_t_vc_02_no_generated_token() -> None:
    capture = _capture(n_gen=0)
    assert capture.states["final_norm"].shape == (0, 4) and capture.n_rows == 0
    assert validate_capture(capture) == []


def test_t_vc_03_one_token() -> None:
    assert validate_capture(_capture(n_gen=1)) == []


def test_t_vc_04_length_ending() -> None:
    assert validate_capture(_capture(finish_reason="length")) == []
    assert set(FINISH_REASONS) == {"eos", "length"}


def test_t_vc_05_finish_reason() -> None:
    for value in (None, "stop"):
        assert _codes(validate_capture(_capture(finish_reason=value))) == ["OBS_FINISH"], value


def test_t_vc_06_token_lists() -> None:
    empty = np.array([], dtype=np.int64)
    assert _codes(validate_capture(_capture(prompt_ids=empty))) == ["OBS_PROMPT_EMPTY"]
    wrong: list[dict[str, Any]] = [
        {"prompt_ids": np.array(PROMPT, dtype=np.int32)},
        {"prompt_ids": np.array([PROMPT], dtype=np.int64)},
        {"prompt_ids": list(PROMPT)},
        {"prompt_ids": np.array([100, -1, 6, 101], dtype=np.int64)},
        {"token_ids": np.array([7, 8, 9], dtype=np.int32)},
    ]
    for override in wrong:
        assert _codes(validate_capture(_capture(**override))) == ["OBS_IDS_TYPE"], override


def test_t_vc_07_non_finite_states() -> None:
    for bad in (np.nan, np.inf, -np.inf):
        states = _capture().states["final_norm"].copy()
        states[1, 2] = bad
        issues = validate_capture(_capture(states=_with(_capture().states, "final_norm", states)))
        assert [(i.code, i.path) for i in issues] == [("OBS_STATE_NONFINITE", "states.final_norm")]


def test_t_vc_08_state_dtype() -> None:
    for dtype in (np.float64, np.float16):
        states = _with(_capture().states, "block_out:1", np.zeros((3, 4), dtype=dtype))
        assert _codes(validate_capture(_capture(states=states))) == ["OBS_STATE_DTYPE"], dtype


def test_t_vc_09_state_columns() -> None:
    for columns in (5, 3):
        states = _with(_capture().states, "final_norm", np.zeros((3, columns), np.float32))
        assert _codes(validate_capture(_capture(states=states))) == ["OBS_STATE_DIM"], columns
    empty = _capture(n_gen=0)
    zero = _with(empty.states, "block_out:1", np.zeros((0, 0), np.float32))
    issues = validate_capture(dataclasses.replace(empty, states=zero))
    assert [(i.code, i.path) for i in issues] == [("OBS_STATE_DIM", "states.block_out:1")]


def test_t_vc_10_state_rows() -> None:
    for rows in (4, 2):
        states = _with(_capture().states, "final_norm", np.zeros((rows, 4), np.float32))
        assert _codes(validate_capture(_capture(states=states))) == ["OBS_STATE_ROWS"], rows


def test_t_vc_11_state_shape() -> None:
    for bad in (np.zeros(4, np.float32), np.zeros((3, 4, 1), np.float32), [[0.0] * 4] * 3):
        states = _with(_capture().states, "final_norm", bad)
        assert _codes(validate_capture(_capture(states=states))) == ["OBS_STATE_TYPE"]


def test_t_vc_12_state_layout() -> None:
    fortran = np.asfortranarray(np.zeros((3, 4), np.float32))
    big_endian = np.zeros((3, 4), dtype=">f4")
    assert not fortran.flags["C_CONTIGUOUS"]
    for bad in (fortran, big_endian):
        issues = validate_capture(_capture(states=_with(_capture().states, "final_norm", bad)))
        # decided: a big-endian float32 is a float32 in the wrong byte order -> LAYOUT, not DTYPE
        assert [(i.code, i.path) for i in issues] == [("OBS_STATE_LAYOUT", "states.final_norm")]


def test_t_vc_13_keys() -> None:
    base = _capture()
    extra = np.zeros((3, 4), np.float32)
    cases = [
        ({"states": _without(base.states, "final_norm")}, "states"),
        ({"states": _with(base.states, "block_out:9", extra)}, "states"),
        ({"row_pos": _without(base.row_pos, "final_norm")}, "row_pos"),
    ]
    for override, path in cases:
        issues = validate_capture(_capture(**override))
        assert [(i.code, i.path) for i in issues] == [("OBS_KEYS", path)]


def test_t_vc_14_rows() -> None:
    base = _capture()
    arr = np.array
    cases = [
        ("row_pos", arr([4, 5, 6], np.int64), "OBS_ROW_MISMATCH"),
        ("row_pos", arr([5, 4, 3], np.int64), "OBS_ROW_MISMATCH"),
        ("row_pos", arr([3, 4, 5], np.int32), "OBS_ROW_TYPE"),
        ("row_pos", arr([3, 4], np.int64), "OBS_ROW_LEN"),
        ("row_decides", arr([0, 1, 3], np.int64), "OBS_ROW_MISMATCH"),
        ("row_decides", arr([-1, 0, 1], np.int64), "OBS_ROW_MISMATCH"),
    ]
    for field, value, code in cases:
        issues = validate_capture(_capture(**{field: _with(getattr(base, field), "final_norm", value)}))
        assert [(i.code, i.path) for i in issues] == [(code, f"{field}.final_norm")]


def test_t_vc_15_row_rule() -> None:
    base = _capture()
    cases = [
        (_without(base.row_rule, "final_norm"), "OBS_KEYS"),
        (_with(base.row_rule, "final_norm", "qwen35-mlx-zzz-out/1"), "OBS_ROW_RULE_UNKNOWN"),
        (_with(base.row_rule, "block_out:1", "qwen35-mlx-mlp-out/1"), "OBS_ROW_RULE_KIND"),
        (_with(base.row_rule, "final_norm", "llama31-mlx-final-norm/1"), "OBS_ROW_RULE_ADAPTER"),
    ]
    for row_rule, code in cases:
        assert _codes(validate_capture(_capture(row_rule=row_rule))) == [code], row_rule


def test_t_vc_16_final_norm_applied() -> None:
    base = _capture()
    cases = [
        (_with(base.final_norm_applied, "block_out:1", UNKNOWN), "OBS_FNA_TYPE"),
        (_with(base.final_norm_applied, "block_out:1", None), "OBS_FNA_TYPE"),
        (_with(base.final_norm_applied, "final_norm", False), "OBS_FNA_DEFINITION"),
    ]
    for value, code in cases:
        assert _codes(validate_capture(_capture(final_norm_applied=value))) == [code]


def test_t_vc_17_texts() -> None:
    for override in ({"model_build_id": "a b"}, {"compute_environment": ""}, {"state_dtype": "float 16"}):
        assert _codes(validate_capture(_capture(**override))) == ["OBS_TEXT"], override


def test_t_vc_18_provenance() -> None:
    runtime = {"backend": "mlx", "mlx": "0.1", "mlx_lm": "0.2"}
    cases = [
        (_prov(weights_sha256="abc"), "OBS_PROV"),
        (_prov(model_ref=""), "OBS_PROV"),
        (_prov(runtime=runtime), "OBS_PROV"),
        (_prov(prompt_ids_sha256="e" * 64), "OBS_PROV_MISMATCH"),
    ]
    for provenance, code in cases:
        assert _codes(validate_capture(_capture(provenance=provenance))) == [code], code
    assert _codes(validate_capture(_capture(provenance="x"))) == ["OBS_PROV"]
    assert _codes(validate_capture(_capture(provenance=_prov(gen_token_ids_sha256="f" * 64)))) == ["OBS_PROV_MISMATCH"]


def test_t_vc_19_unknowns() -> None:
    assert _codes(validate_capture(_capture(provenance=_prov(revision=None)))) == ["OBS_UNKNOWNS"]
    assert _codes(validate_capture(_capture(unknowns=("provenance.nothing",)))) == ["OBS_UNKNOWNS"]
    listed = _capture(provenance=_prov(revision=None), unknowns=("provenance.revision",))
    assert validate_capture(listed) == []
    both = _capture(provenance=_prov(revision=None), state_dtype=UNKNOWN, unknowns=("state_dtype", "provenance.revision"))
    assert _codes(validate_capture(both)) == ["OBS_UNKNOWNS"]  # not ascending


def test_t_vc_20_against_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    caps = qwen35_mlx_capabilities(n_layers=2, dimension=4, native_dtype="bfloat16")
    assert validate_capture(_capture(), caps) == []
    assert "OBS_CAP_ADAPTER" in _codes(validate_capture(_capture(adapter="llama31-mlx-capture"), caps))
    wide = qwen35_mlx_capabilities(n_layers=2, dimension=5, native_dtype="bfloat16")
    assert _codes(validate_capture(_capture(), wide)) == ["OBS_CAP_DIM"]
    narrow = qwen35_mlx_capabilities(n_layers=1, dimension=4, native_dtype="bfloat16")
    undeclared = validate_capture(_capture(), narrow)
    assert [(i.code, i.path) for i in undeclared] == [("OBS_CAP_POINT_UNDECLARED", "points.block_out:1")]
    fna = caps.final_norm_applied
    claims_true = dataclasses.replace(caps, final_norm_applied=_with(fna, "block_out:1", True))
    assert _codes(validate_capture(_capture(), claims_true)) == ["OBS_CAP_FNA"]
    claims_unknown = dataclasses.replace(
        caps, final_norm_applied=_with(fna, "block_out:1", UNKNOWN), unknowns=("final_norm_applied.block_out:1",)
    )
    assert _codes(validate_capture(_capture(), claims_unknown)) == ["OBS_CAP_FNA"]
    version2 = RowRuleSpec("qwen35-mlx-block-out/2", "block_out", "qwen35-mlx-capture", ALIGNMENT_DECIDES_NEXT, "t")
    monkeypatch.setattr(observation, "ROW_RULES", MappingProxyType({**ROW_RULES, version2.name: version2}))
    declares_v2 = dataclasses.replace(caps, row_rule=_with(caps.row_rule, "block_out:1", version2.name))
    assert _codes(validate_capture(_capture(), declares_v2)) == ["OBS_CAP_ROW_RULE"]


def test_t_vc_21_invalid_capabilities_still_check_the_capture() -> None:
    bad = qwen35_mlx_capabilities(n_layers=2, dimension=4, native_dtype="bfloat16")
    bad = dataclasses.replace(bad, runtime="")
    assert _codes(validate_capture(_capture(), bad)) == ["OBS_CAP_INVALID"]
    assert _codes(validate_capture(_capture(finish_reason="stop"), bad)) == ["OBS_FINISH", "OBS_CAP_INVALID"]


def test_t_vc_22_not_a_capture() -> None:
    assert _codes(validate_capture("x")) == ["OBS_TYPE"] and len(validate_capture("x")) == 1


def test_t_vc_23_all_issues_and_no_side_effect() -> None:
    nan_states = np.zeros((3, 4), np.float32)
    nan_states[0, 0] = np.nan
    capture = _capture(
        model_build_id="a b",
        finish_reason="stop",
        states=_with(_capture().states, "final_norm", nan_states),
    )
    before = {n: a.tobytes() for n, a in capture.states.items()}
    issues = validate_capture(capture)
    assert _codes(issues) == ["OBS_TEXT", "OBS_FINISH", "OBS_STATE_NONFINITE"]
    assert {n: a.tobytes() for n, a in capture.states.items()} == before
    assert capture.model_build_id == "a b" and capture.finish_reason == "stop"
    assert capture.token_ids.tolist() == [7, 8, 9] and capture.prompt_ids.tolist() == PROMPT


def test_t_vc_24_ensure_valid() -> None:
    ensure_valid([])
    issue = ObservationIssue("OBS_TYPE", "x", "message")
    with pytest.raises(ObservationError) as info:
        ensure_valid([issue])
    assert info.value.issues == (issue,) and isinstance(info.value, ValueError)
    assert "OBS_TYPE" in str(info.value) and "1" in str(info.value)


# ---- 7.5 conversions -----------------------------------------------------------------------------


def test_t_fl_01_llama_conversion(tmp_path: Path) -> None:
    capture = _llama_capture(tmp_path)
    assert validate_capture(capture) == []
    assert capture.adapter == "llama31-mlx-capture" and capture.points == ("final_norm",)
    assert capture.dimension == 4096 and capture.n_rows == capture.n_gen == 3
    assert capture.row_rule == {"final_norm": "llama31-mlx-final-norm/1"}
    assert capture.final_norm_applied == {"final_norm": True} and capture.state_dtype == "bfloat16"
    assert capture.finish_reason == "eos" and EOS not in capture.token_ids.tolist()
    assert capture.model_build_id == LLAMA_BUILD and capture.compute_environment == "mlx-4bit"
    assert capture.states["final_norm"].dtype == np.float32 and capture.provenance.runtime["backend"] == "mlx"


def test_t_fl_02_llama_rows_follow_the_row_rule(tmp_path: Path) -> None:
    capture = _llama_capture(tmp_path)
    states = capture.states["final_norm"]
    assert capture.token_ids.tolist() == [7, 8, 9]
    assert np.array_equal(states[0], _llama_state(PROMPT[-1], 3))
    for i in range(1, capture.n_gen):
        assert np.array_equal(states[i], _llama_state(int(capture.token_ids[i - 1]), 3 + i))
    assert capture.row_pos["final_norm"].tolist() == [3, 4, 5]
    assert capture.row_decides["final_norm"].tolist() == list(range(capture.n_gen))


def test_t_fl_03_length_limit_is_convertible(tmp_path: Path) -> None:
    result = _llama_result(tmp_path, [], max_tokens=2)
    assert result.finish_reason == "length" and result.ok is False
    capture = from_llama31(result, model_build_id=LLAMA_BUILD, compute_environment="mlx-4bit")
    assert capture.finish_reason == "length" and capture.n_rows == 2


def test_t_fl_04_no_generated_token(tmp_path: Path) -> None:
    result = _llama_result(tmp_path, [EOS])
    assert result.token_ids == [] and result.states.shape == (0, 4096) and result.finish_reason == "eos"
    capture = from_llama31(result, model_build_id=LLAMA_BUILD, compute_environment="mlx-4bit")
    assert capture.n_rows == 0 and capture.states["final_norm"].shape == (0, 4096)


def test_t_fl_05_not_convertible(tmp_path: Path) -> None:
    no_tokens = _llama_result(tmp_path, [7], max_tokens=0)
    assert no_tokens.finish_reason is None
    assert _raised(from_llama31, no_tokens, model_build_id=LLAMA_BUILD, compute_environment="e") == ["OBS_SRC_FAILED"]

    def boom(_target: str) -> Any:
        raise OSError("no model")

    failed = Llama31MLXCaptureProvider("x", loader=boom, snapshot_dir=tmp_path).capture_chat(MSG, max_tokens=4)
    assert failed.failure_kind == "load_failed"
    assert _raised(from_llama31, failed, model_build_id=LLAMA_BUILD, compute_environment="e") == ["OBS_SRC_FAILED"]
    assert _raised(from_llama31, object(), model_build_id=LLAMA_BUILD, compute_environment="e")[0] == "OBS_SRC_FIELD"


def test_t_fl_06_changed_row_rule_text(tmp_path: Path) -> None:
    result = _llama_result(tmp_path, [7, EOS])
    changed = dataclasses.replace(result, row_rule=result.row_rule.replace("row i", "row j", 1))
    assert _raised(from_llama31, changed, model_build_id=LLAMA_BUILD, compute_environment="e") == ["OBS_SRC_ROW_RULE"]


def test_t_fl_07_arrays_are_copied(tmp_path: Path) -> None:
    result = _llama_result(tmp_path, [7, 8, EOS])
    capture = from_llama31(result, model_build_id=LLAMA_BUILD, compute_environment="mlx-4bit")
    expected = result.states[0, 0]
    result.states[0, 0] = 9e9
    assert capture.states["final_norm"][0, 0] == expected
    with pytest.raises(ValueError):
        capture.states["final_norm"][0, 0] = 1.0
    with pytest.raises(ValueError):
        capture.prompt_ids[0] = 1
    with pytest.raises(TypeError):
        capture.states["x"] = capture.states["final_norm"]  # type: ignore[index]
    result.prompt_ids.append(5)
    assert capture.prompt_ids.tolist() == PROMPT


def test_t_fl_08_provenance(tmp_path: Path) -> None:
    capture = _llama_capture(tmp_path)
    assert capture.provenance.prompt_ids_sha256 == input_ids_sha256(PROMPT)
    assert capture.provenance.gen_token_ids_sha256 == input_ids_sha256([7, 8, 9])
    assert capture.provenance.eos_ids == (EOS,) and "provenance.eos_ids" not in capture.unknowns
    assert capture.provenance.revision is None and "provenance.revision" in capture.unknowns
    assert capture.provenance.chat_template_sha256 == hashlib.sha256(b"{{ messages }}").hexdigest()
    assert capture.provenance.special_tokens_in == ((0, 100),)
    assert list(capture.unknowns) == sorted(capture.unknowns)
    with_revision = from_llama31(
        _llama_result(tmp_path, [7, EOS], revision="a" * 40), model_build_id=LLAMA_BUILD, compute_environment="e"
    )
    assert with_revision.provenance.revision == "a" * 40 and "provenance.revision" not in with_revision.unknowns
    empty = from_llama31(_llama_result(tmp_path, [EOS]), model_build_id=LLAMA_BUILD, compute_environment="e")
    assert empty.provenance.gen_token_ids_sha256 == hashlib.sha256(b"").hexdigest()


def test_t_fl_09_bad_identifiers(tmp_path: Path) -> None:
    result = _llama_result(tmp_path, [7, EOS])
    assert _raised(from_llama31, result, model_build_id="bad id", compute_environment="mlx-4bit") == ["OBS_TEXT"]
    assert _raised(from_llama31, result, model_build_id=LLAMA_BUILD, compute_environment="") == ["OBS_TEXT"]


def test_t_fl_10_llama_capture_matches_its_capabilities(tmp_path: Path) -> None:
    capture = _llama_capture(tmp_path)
    assert validate_capture(capture, llama31_mlx_capabilities(native_dtype="bfloat16")) == []
    assert "OBS_CAP_FNA" not in _codes(validate_capture(capture, llama31_mlx_capabilities()))


def test_t_fq_01_qwen_conversion(tmp_path: Path) -> None:
    capture = _qwen_capture(tmp_path)
    assert validate_capture(capture) == []
    assert capture.points == ("mlp_out:15", "mlp_out:19", "block_out:15", "block_out:19", "final_norm")
    assert capture.dimension == QWEN_DIM and capture.adapter == "qwen35-mlx-capture"
    for name in capture.points:
        assert capture.states[name].shape == (capture.n_gen, QWEN_DIM)
    assert capture.row_rule["mlp_out:15"] == "qwen35-mlx-mlp-out/1"
    assert capture.row_rule["block_out:19"] == "qwen35-mlx-block-out/1"
    assert capture.row_rule["final_norm"] == "qwen35-mlx-final-norm/1"
    assert [n for n, v in capture.final_norm_applied.items() if v] == ["final_norm"]
    assert capture.provenance.eos_ids == (EOS2, EOS) and capture.provenance.chat_template_kwargs == {"enable_thinking": True}
    assert capture.provenance.sampler["presence_penalty"] == 1.5


def test_t_fq_02_qwen_rows_per_point(tmp_path: Path) -> None:
    capture = _qwen_capture(tmp_path)
    assert capture.n_gen == 3
    for i, name in enumerate(capture.points):
        states = capture.states[name]
        assert np.array_equal(states[0], _qwen_state(PROMPT[-1], 3, 0.25 * i)), name
        for r in range(1, capture.n_gen):
            assert np.array_equal(states[r], _qwen_state(int(capture.token_ids[r - 1]), 3 + r, 0.25 * i)), name
        assert capture.row_pos[name].tolist() == [3, 4, 5] and capture.row_decides[name].tolist() == [0, 1, 2]


def test_t_fq_03_subsets_of_points(tmp_path: Path) -> None:
    one = _qwen_result(tmp_path, [7, 8, EOS], positions=(CapturePosition("block_out", 3),))
    capture = from_qwen35(one, model_build_id=QWEN_BUILD, compute_environment="mlx-bf16-metal")
    assert capture.points == ("block_out:3",) and capture.n_rows == 2
    no_final = _qwen_result(tmp_path, [7, EOS], positions=PILOT_POSITIONS[:4])
    capture = from_qwen35(no_final, model_build_id=QWEN_BUILD, compute_environment="mlx-bf16-metal")
    assert "final_norm" not in capture.points and len(capture.points) == 4


def test_t_fq_04_broken_positions(tmp_path: Path) -> None:
    result = _qwen_result(tmp_path, [7, 8, EOS])

    def convert(changed: Any) -> list[str]:
        return _raised(from_qwen35, changed, model_build_id=QWEN_BUILD, compute_environment="e")

    fewer_states = {k: v for k, v in result.states.items() if k != "final_norm"}
    assert convert(dataclasses.replace(result, states=fewer_states)) == ["OBS_SRC_POSITIONS"]
    wrong_rule = [dict(p) for p in result.positions]
    wrong_rule[0]["row_rule"] = "qwen35-mlx-block-out/1"  # position 0 is mlp_out
    assert convert(dataclasses.replace(result, positions=wrong_rule)) == ["OBS_SRC_POSITIONS"]
    wrong_name = [dict(p) for p in result.positions]
    wrong_name[1]["name"] = "L99.mlp_out"
    assert convert(dataclasses.replace(result, positions=wrong_name)) == ["OBS_SRC_POSITIONS"]
    missing_key = [{k: v for k, v in p.items() if k != "kind"} for p in result.positions]
    assert convert(dataclasses.replace(result, positions=missing_key)) == ["OBS_SRC_POSITIONS"] * 5
    wrong_text = dataclasses.replace(result, row_rule="something else")
    assert convert(wrong_text) == ["OBS_SRC_ROW_RULE"]


def test_t_fq_05_dimension_cannot_be_determined(tmp_path: Path) -> None:
    result = _qwen_result(tmp_path, [EOS])
    assert result.token_ids == []
    unreadable = dataclasses.replace(
        result, hidden_size=None, states={n: np.zeros((0, 0), np.float32) for n in result.states}
    )
    codes = _raised(from_qwen35, unreadable, model_build_id=QWEN_BUILD, compute_environment="e")
    assert codes == ["OBS_STATE_DIM"]
    readable = from_qwen35(result, model_build_id=QWEN_BUILD, compute_environment="e")
    assert readable.n_rows == 0 and readable.dimension == QWEN_DIM
    no_hidden = dataclasses.replace(_qwen_result(tmp_path, [7, EOS]), hidden_size=None)
    assert from_qwen35(no_hidden, model_build_id=QWEN_BUILD, compute_environment="e").dimension == QWEN_DIM


def test_t_fq_06_prompt_hash_must_match(tmp_path: Path) -> None:
    result = _qwen_result(tmp_path, [7, EOS])
    assert result.prompt_ids_sha256 == input_ids_sha256(PROMPT)
    changed = dataclasses.replace(result, prompt_ids_sha256="0" * 64)
    assert _raised(from_qwen35, changed, model_build_id=QWEN_BUILD, compute_environment="e") == ["OBS_PROV_MISMATCH"]


def test_t_fq_07_eos_among_the_tokens(tmp_path: Path) -> None:
    result = _qwen_result(tmp_path, [7, 8, EOS])
    for eos in (EOS, EOS2):
        mixed = dataclasses.replace(result, token_ids=[7, eos, 8])
        assert _raised(from_qwen35, mixed, model_build_id=QWEN_BUILD, compute_environment="e") == ["OBS_SRC_EOS"]


def test_t_fq_08_qwen_capture_matches_its_capabilities(tmp_path: Path) -> None:
    capture = _qwen_capture(tmp_path)
    caps = qwen35_mlx_capabilities(n_layers=24, dimension=QWEN_DIM, native_dtype="bfloat16")
    assert validate_capture(capture, caps) == []
    small = qwen35_mlx_capabilities(n_layers=16, dimension=QWEN_DIM, native_dtype="bfloat16")
    issues = validate_capture(capture, small)
    assert [(i.code, i.path) for i in issues] == [
        ("OBS_CAP_POINT_UNDECLARED", "points.mlp_out:19"),
        ("OBS_CAP_POINT_UNDECLARED", "points.block_out:19"),
    ]


# ---- 7.6 responsibility boundary and regression --------------------------------------------------

_DESIGN_NAMES = {
    # constants
    "KINDS", "RESERVED_KINDS", "TOKEN_SCOPES", "DELIVERIES", "EQUIVALENCE_CHECKS", "FINISH_REASONS",
    "UNKNOWN", "ALIGNMENT_DECIDES_NEXT", "SPACE_RULE", "ROW_RULES",
    # types
    "ObservationPoint", "RowRuleSpec", "CaptureCapabilities", "CaptureRequest", "CaptureProvenance",
    "ObservationCapture", "ObservationIssue", "ObservationError",
    # functions
    "point_from_name", "point_from_legacy_name", "row_positions",
    "validate_capabilities", "validate_request", "validate_capture", "ensure_valid",
    "llama31_mlx_capabilities", "qwen35_mlx_capabilities", "from_llama31", "from_qwen35",
    "space_materials", "space_collisions",
}  # fmt: skip


def _child_env() -> dict[str, str]:
    source_root = str(Path(observation.__file__).resolve().parents[1])
    existing = os.environ.get("PYTHONPATH")
    return {**os.environ, "PYTHONPATH": source_root + (os.pathsep + existing if existing else "")}


def test_t_bd_01_public_names() -> None:
    assert set(observation.__all__) == _DESIGN_NAMES
    assert len(observation.__all__) == len(_DESIGN_NAMES)
    for name in observation.__all__:
        assert hasattr(observation, name)


def test_t_bd_02_no_runtime_is_imported() -> None:
    code = (
        "import json, sys\n"
        "import sensos_inference.observation\n"
        "heavy = ('mlx', 'mlx_lm', 'torch', 'transformers', 'vllm')\n"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in heavy\n"
        "             or m == 'sensos_inference.providers' or m.startswith('sensos_inference.providers.'))\n"
        "print(json.dumps(bad))\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=_child_env(), check=True)
    assert json.loads(done.stdout.strip().splitlines()[-1]) == []


def test_t_bd_03_no_write_entry_point() -> None:
    forbidden = {"model", "engine", "cache", "hook"}
    functions = [getattr(observation, n) for n in observation.__all__ if inspect.isfunction(getattr(observation, n))]
    assert len(functions) == 13
    for function in functions:
        names = set(inspect.signature(function).parameters)
        assert not names & forbidden, function.__name__
    for cls in (ObservationPoint, CaptureCapabilities, CaptureRequest, CaptureProvenance, ObservationCapture):
        assert not {f.name for f in dataclasses.fields(cls)} & forbidden, cls.__name__
        assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_t_bd_04_package_exports_are_unchanged() -> None:
    assert sorted(sensos_inference.__all__) == sorted(
        ["EOS_MISSING", "GENERATE_FAILED", "LENGTH_LIMIT", "LOAD_FAILED", "InferenceProvider", "InferenceResult"]
    )


def test_t_bd_05_existing_tests_still_pass() -> None:
    here = Path(__file__).resolve().parent
    files = ["test_llama31_capture.py", "test_llama31_provider.py", "test_qwen35_capture.py", "test_sampling.py"]
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *(str(here / f) for f in files)]
    done = subprocess.run(command, capture_output=True, text=True, env=_child_env(), cwd=here)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-500:]
