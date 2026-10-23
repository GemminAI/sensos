"""Llama31MLXCaptureProvider without a model: a fake engine and a fake tokenizer stand in for MLX."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from sensos_inference import LENGTH_LIMIT
from sensos_inference.providers.llama31_mlx import Llama31MLXProvider
from sensos_inference.providers.llama31_mlx_capture import (
    HIDDEN_DIMENSION,
    ROW_RULE,
    Llama31MLXCaptureProvider,
    input_ids_sha256,
    snapshot_revision,
    special_tokens_in,
    tokenizer_sha256,
    weights_sha256,
)

VOCAB = 40
EOS = 39
PROMPT = [100, 5, 6, 101]


def _logprobs(token: int) -> np.ndarray:
    scores = np.cos(np.arange(VOCAB) * (token + 1) * 0.37)
    return scores - np.log(np.exp(scores).sum())


def _state(token: int, position: int) -> np.ndarray:
    return np.full(HIDDEN_DIMENSION, token * 1000.0 + position, dtype=np.float32)


class _Engine:
    """Position-aware: a state is a function of the fed token and its position, like a real model's."""

    state_dtype = "bfloat16"

    def __init__(self) -> None:
        self.position = 0
        self.prefilled: list[int] = []

    def prefill(self, ids):  # type: ignore[no-untyped-def]
        self.prefilled = list(ids)
        self.position = len(ids)

    def step(self, token):  # type: ignore[no-untyped-def]
        out = _logprobs(token), _state(token, self.position)
        self.position += 1
        return out


@dataclass
class _Added:
    special: bool


class _Tok:
    chat_template = "{{ messages }}"
    eos_token_ids = {EOS}
    all_special_ids = [100]
    added_tokens_decoder = {101: _Added(True), 7: _Added(False)}

    def apply_chat_template(self, messages, add_generation_prompt, tokenize):  # type: ignore[no-untyped-def]
        return list(PROMPT)

    def decode(self, ids):  # type: ignore[no-untyped-def]
        return " ".join(str(i) for i in ids)


def _provider(tmp_path: Path, **kwargs) -> Llama31MLXCaptureProvider:  # type: ignore[no-untyped-def]
    snapshot = tmp_path / "snap"
    snapshot.mkdir(exist_ok=True)
    (snapshot / "tokenizer.json").write_text('{"a":1}')
    (snapshot / "tokenizer_config.json").write_text('{"b":2}')
    (snapshot / "model.safetensors").write_bytes(b"weights")
    return Llama31MLXCaptureProvider(
        "local/model",
        loader=lambda _t: (object(), _Tok()),
        engine_factory=lambda _m: _Engine(),
        snapshot_dir=snapshot,
        hash_cache_dir=tmp_path / "hashes",
        **kwargs,
    )


def test_rows_follow_the_row_rule_and_eos_gives_no_row(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat([{"role": "user", "content": "x"}], max_tokens=64, seed=3)
    assert result.row_rule == ROW_RULE
    assert result.prompt_ids == PROMPT and result.token_ids
    n = len(result.token_ids)
    assert result.states.shape == (n, HIDDEN_DIMENSION) and result.states.dtype == np.float32
    assert result.state_dtype == "bfloat16"
    # row 0 is the state at the last prompt position; row i the state at the position of token_ids[i-1]
    assert np.array_equal(result.states[0], _state(PROMPT[-1], len(PROMPT) - 1))
    for i in range(1, n):
        assert np.array_equal(result.states[i], _state(result.token_ids[i - 1], len(PROMPT) - 1 + i))
    if result.finish_reason == "eos":
        assert EOS not in result.token_ids and result.ok


def test_token_ids_equal_those_of_the_stream_provider(tmp_path: Path) -> None:
    from sensos_inference.sampling import HFOrderSampler

    def stream(model, tok, prompt, max_tokens, sampler):  # type: ignore[no-untyped-def]
        from dataclasses import make_dataclass

        resp = make_dataclass("R", [("token", int), ("finish_reason", str | None)])
        last = prompt[-1]
        for _ in range(max_tokens):
            last = int(sampler(_logprobs(last)))
            yield resp(last, None)

    reference = Llama31MLXProvider(
        "local/model", loader=lambda _t: (object(), _Tok()), stream=stream
    ).generate_chat([{"role": "user", "content": "x"}], max_tokens=64, seed=11)
    # the stream provider wraps the sampler for mx; with mlx absent it is called as-is
    captured = _provider(tmp_path).capture_chat([{"role": "user", "content": "x"}], max_tokens=64, seed=11)
    assert captured.token_ids == reference.token_ids
    assert captured.finish_reason == reference.finish_reason
    assert HFOrderSampler is not None


def test_length_limit_gives_one_row_per_token(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat([{"role": "user", "content": "x"}], max_tokens=2, seed=1)
    if result.finish_reason == "length":
        assert result.failure_kind == LENGTH_LIMIT and len(result.token_ids) == 2
        assert result.states.shape[0] == 2


def test_hash_rules(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat([{"role": "user", "content": "x"}], max_tokens=4, seed=2)
    snap = tmp_path / "snap"
    expected = hashlib.sha256()
    for name in ("tokenizer.json", "tokenizer_config.json"):  # ascending, existing ones only
        expected.update(name.encode() + b"\0" + (snap / name).read_bytes() + b"\0")
    assert result.tokenizer_sha256 == expected.hexdigest() == tokenizer_sha256(snap)
    assert result.weights_sha256 == hashlib.sha256(b"model.safetensors\0weights\0").hexdigest()
    assert result.chat_template_sha256 == hashlib.sha256(b"{{ messages }}").hexdigest()
    assert result.special_tokens_in == [[0, 100], [3, 101]]  # 7 is added but not special; 5, 6 are plain


def test_special_tokens_rule_is_position_ascending() -> None:
    assert special_tokens_in([9, 3, 9, 4], [9, 4]) == [[0, 9], [2, 9], [3, 4]]
    assert special_tokens_in([1, 2], []) == []


def test_weights_hash_is_cached_and_invalidated_by_a_change(tmp_path: Path) -> None:
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "a.safetensors").write_bytes(b"one")
    cache = tmp_path / "cache"
    first = weights_sha256(snap, cache)
    assert first == hashlib.sha256(b"a.safetensors\0one\0").hexdigest()
    (cache / next(cache.iterdir()).name).write_text(
        json.dumps({"files": json.loads(next(cache.iterdir()).read_text())["files"], "weights_sha256": "f" * 64})
    )
    assert weights_sha256(snap, cache) == "f" * 64  # served from the cache file
    (snap / "a.safetensors").write_bytes(b"three")
    assert weights_sha256(snap, cache) == hashlib.sha256(b"a.safetensors\0three\0").hexdigest()
    assert weights_sha256(tmp_path / "empty-nonexistent", cache) is None


def test_revision_comes_from_download_metadata(tmp_path: Path) -> None:
    meta = tmp_path / ".cache" / "huggingface" / "download"
    meta.mkdir(parents=True)
    (meta / "config.json.metadata").write_text("a" * 40 + "\netag\n123\n")
    (meta / "x.metadata").write_text("a" * 40 + "\netag\n123\n")
    assert snapshot_revision(tmp_path) == "a" * 40
    (meta / "y.metadata").write_text("b" * 40 + "\n")
    assert snapshot_revision(tmp_path) is None  # they disagree


def test_input_ids_hash_is_little_endian_int64() -> None:
    assert input_ids_sha256([1, 2]) == hashlib.sha256(
        (1).to_bytes(8, "little") + (2).to_bytes(8, "little")
    ).hexdigest()
