"""Qwen35MLXCaptureProvider without a model: a fake engine and a fake tokenizer stand in for MLX."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

from sensos_inference import LENGTH_LIMIT
from sensos_inference.outcome import outcome, repetition_condition
from sensos_inference.providers.qwen35_mlx_capture import (
    PILOT_POSITIONS,
    ROW_RULES,
    CapturePosition,
    Qwen35MLXCaptureProvider,
    check_positions,
    run_multi_capture_loop,
)
from sensos_inference.sampling import HFOrderSampler, PresencePenaltySampler

VOCAB = 40
EOS = 39
EOS2 = 38
DIM = 6  # not 4096 on purpose
PROMPT = [100, 5, 6, 101]


def _logprobs(token: int) -> np.ndarray:
    scores = np.cos(np.arange(VOCAB) * (token + 1) * 0.37)
    return scores - np.log(np.exp(scores).sum())


def _state(token: int, position: int, salt: float) -> np.ndarray:
    return np.full(DIM, token * 1000.0 + position + salt, dtype=np.float32)


class _Engine:
    state_dtype = "bfloat16"

    def __init__(self, positions) -> None:  # type: ignore[no-untyped-def]
        self.positions = positions
        self.position = 0

    def prefill(self, ids):  # type: ignore[no-untyped-def]
        self.position = len(ids)

    def step(self, token):  # type: ignore[no-untyped-def]
        states = {p.name: _state(token, self.position, 0.25 * i) for i, p in enumerate(self.positions)}
        self.position += 1
        return _logprobs(token), states


@dataclass
class _Args:
    hidden_size: int = DIM


class _LM:
    args = _Args()


class _Model:
    language_model = _LM()

    class args:  # noqa: N801
        text_config = {"eos_token_id": EOS2, "hidden_size": DIM}


class _Tok:
    chat_template = "{{ messages }}"
    eos_token_ids = {EOS}
    all_special_ids = [100]
    added_tokens_decoder: ClassVar[dict] = {}
    seen_kwargs: ClassVar[dict] = {}

    def apply_chat_template(self, messages, add_generation_prompt, tokenize, **kwargs):  # type: ignore[no-untyped-def]
        _Tok.seen_kwargs = kwargs
        return list(PROMPT)

    def decode(self, ids):  # type: ignore[no-untyped-def]
        return " ".join(str(i) for i in ids)


def _provider(tmp_path: Path) -> Qwen35MLXCaptureProvider:
    snap = tmp_path / "snap"
    snap.mkdir(exist_ok=True)
    (snap / "tokenizer.json").write_text("{}")
    (snap / "model.safetensors").write_bytes(b"w")
    return Qwen35MLXCaptureProvider(
        "local/qwen",
        loader=lambda _t: (_Model(), _Tok()),
        engine_factory=lambda _m, pos: _Engine(pos),
        snapshot_dir=snap,
        hash_cache_dir=tmp_path / "h",
    )


MSG = [{"role": "user", "content": "x"}]


def test_positions_naming_and_validation() -> None:
    assert [p.name for p in PILOT_POSITIONS] == [
        "L15.mlp_out", "L19.mlp_out", "L15.block_out", "L19.block_out", "final_norm"
    ]  # fmt: skip
    assert [p.layer_label for p in PILOT_POSITIONS] == [15, 19, 15, 19, "final_norm"]
    assert PILOT_POSITIONS[0].row_rule != PILOT_POSITIONS[2].row_rule  # same layer, different spaces
    assert set(ROW_RULES) == {"mlp_out", "block_out", "final_norm"}
    for bad in (("bogus", 1), ("mlp_out", None), ("mlp_out", -1), ("mlp_out", True), ("final_norm", 3)):
        with pytest.raises(ValueError):
            CapturePosition(*bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        check_positions([], 24)
    with pytest.raises(ValueError):
        check_positions([PILOT_POSITIONS[0], PILOT_POSITIONS[0]], 24)
    with pytest.raises(ValueError):
        check_positions([CapturePosition("mlp_out", 24)], 24)


def test_rows_follow_the_row_rule_per_position(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat(MSG, max_tokens=64, seed=3)
    n = len(result.token_ids)
    assert n and result.hidden_size == DIM and result.state_dtype == "bfloat16"
    assert set(result.states) == {p.name for p in PILOT_POSITIONS}
    for i, p in enumerate(PILOT_POSITIONS):
        arr = result.states[p.name]
        assert arr.shape == (n, DIM) and arr.dtype == np.float32  # D from the config, not 4096
        assert np.array_equal(arr[0], _state(PROMPT[-1], len(PROMPT) - 1, 0.25 * i))
        for r in range(1, n):
            assert np.array_equal(arr[r], _state(result.token_ids[r - 1], len(PROMPT) - 1 + r, 0.25 * i))
    assert {d["name"]: d["layer"] for d in result.positions}["final_norm"] == "final_norm"
    assert {d["name"]: d["row_rule"] for d in result.positions}["L15.mlp_out"] == ROW_RULES["mlp_out"]
    if result.finish_reason == "eos":
        assert not {EOS, EOS2} & set(result.token_ids)


def test_both_eos_ids_end_the_generation_and_template_kwargs_are_passed(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat(MSG, max_tokens=512, seed=4, enable_thinking=True)
    assert _Tok.seen_kwargs == {"enable_thinking": True}
    assert result.chat_template_kwargs == {"enable_thinking": True}
    assert result.eos_ids == [EOS2, EOS]


def test_length_limit_is_recorded_apart_from_repetition(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat(MSG, max_tokens=2, seed=1)
    if result.finish_reason == "length":
        assert result.failure_kind == LENGTH_LIMIT and len(result.token_ids) == 2
        assert result.outcome["reached_max_length"] is True
        assert result.outcome["repetition"]["evaluated"] is False  # fewer than 1024 tokens


def test_run_loop_returns_none_finish_for_zero_tokens_and_rejects_empty_prompt() -> None:
    eng = _Engine(PILOT_POSITIONS)
    assert run_multi_capture_loop(eng, PROMPT, HFOrderSampler(temperature=1, top_k=0, top_p=1, seed=0), {EOS}, 0, ["x"])[2] is None
    with pytest.raises(ValueError):
        run_multi_capture_loop(eng, [], lambda _l: 0, {EOS}, 4, ["x"])


def test_load_failure_is_reported(tmp_path: Path) -> None:
    def boom(_t):  # type: ignore[no-untyped-def]
        raise OSError("no model")

    prov = Qwen35MLXCaptureProvider("x", loader=boom, snapshot_dir=tmp_path)
    result = prov.capture_chat(MSG, max_tokens=4)
    assert not result.ok and result.failure_kind == "load_failed"


# ---- sampler and outcome ---------------------------------------------------------------------


def test_presence_penalty_zero_is_the_plain_sampler() -> None:
    a = HFOrderSampler(temperature=0.6, top_k=20, top_p=0.95, seed=5)
    b = PresencePenaltySampler(temperature=0.6, top_k=20, top_p=0.95, seed=5, presence_penalty=0.0)
    rows = [_logprobs(t) for t in range(30)]
    assert [a(r) for r in rows] == [b(r) for r in rows]


def test_presence_penalty_lowers_only_seen_generated_tokens() -> None:
    s = PresencePenaltySampler(temperature=1.0, top_k=0, top_p=1.0, seed=0, presence_penalty=100.0)
    row = np.zeros(8)
    row[3] = 5.0
    draws = [s(row) for _ in range(8)]
    assert draws[0] == 3  # first draw: nothing seen yet, token 3 dominates
    assert sorted(draws) == list(range(8))  # each seen token is pushed down by 100: a permutation
    assert s.settings()["presence_penalty"] == 100.0
    assert s.settings()["order"][0] == "presence_penalty"


def test_repetition_condition_and_outcome() -> None:
    looped = list(range(10)) + [1, 2, 3, 4] * 400
    cond = repetition_condition(looped)
    assert cond["evaluated"] and cond["met"] and cond["distinct_ratio"] < 0.2
    varied = list(range(3000))
    assert repetition_condition(varied)["evaluated"] and not repetition_condition(varied)["met"]
    short = repetition_condition([1] * 100)
    assert short == {**short, "evaluated": False, "met": False}
    assert repetition_condition([1] * 5, tail=4, n=8)["evaluated"] is False  # tail < n
    both = outcome(looped, "length")
    assert both["reached_max_length"] is True and both["repetition"]["met"] is True
    only_len = outcome(varied, "length")
    assert only_len["reached_max_length"] and not only_len["repetition"]["met"]
    only_rep = outcome(looped, "eos")
    assert not only_rep["reached_max_length"] and only_rep["repetition"]["met"]
