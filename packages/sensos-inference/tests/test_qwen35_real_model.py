"""Real-model checks for ``Qwen35MLXCaptureProvider``. Skipped unless ``QWEN35_SNAPSHOT`` names a
local ``Qwen/Qwen3.5-0.8B`` snapshot directory and ``mlx_lm`` is installed (MLX, Apple silicon)."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

SNAPSHOT = os.environ.get("QWEN35_SNAPSHOT")
pytestmark = pytest.mark.skipif(not SNAPSHOT, reason="QWEN35_SNAPSHOT not set")

MESSAGES = [
    {
        "role": "user",
        "content": "What is 12*13? Please reason step by step, and put your final answer within \\boxed{}.",
    }
]
SAMPLING = {"temperature": 0.6, "top_k": 20, "top_p": 0.95, "presence_penalty": 1.5, "seed": 7}


@pytest.fixture(scope="module")
def provider():  # type: ignore[no-untyped-def]
    from sensos_inference.providers.qwen35_mlx_capture import Qwen35MLXCaptureProvider

    prov = Qwen35MLXCaptureProvider("qwen35-real", snapshot_dir=Path(SNAPSHOT or ""))
    prov._ensure_loaded_from(prov._load_target())
    return prov


def _prompt_ids(prov) -> list[int]:  # type: ignore[no-untyped-def]
    ids = prov._tokenizer.apply_chat_template(
        MESSAGES, add_generation_prompt=True, tokenize=True, enable_thinking=True
    )
    return [int(i) for i in (ids["input_ids"] if hasattr(ids, "keys") else ids)]


def test_hidden_size_comes_from_config(provider) -> None:  # type: ignore[no-untyped-def]
    assert provider.hidden_size() == 1024


def test_engine_forward_is_the_models_forward(provider) -> None:  # type: ignore[no-untyped-def]
    from sensos_inference.providers.qwen35_mlx_capture import Qwen35MLXEngine

    diff = Qwen35MLXEngine(provider._model).check_equivalence(_prompt_ids(provider))
    assert diff == {"final_norm_max_abs_diff": 0.0, "logits_max_abs_diff": 0.0}


def _reference_tokens(prov, n: int) -> list[int]:  # type: ignore[no-untyped-def]
    """Generation WITHOUT capture: the model's own ``__call__`` and cache, same sampler and float32
    log-softmax; no taps, no state is read."""
    import mlx.core as mx

    from sensos_inference.sampling import PresencePenaltySampler

    model, eos = prov._model, prov._eos_ids()
    sampler = PresencePenaltySampler(
        temperature=SAMPLING["temperature"], top_k=SAMPLING["top_k"], top_p=SAMPLING["top_p"],
        seed=SAMPLING["seed"], presence_penalty=SAMPLING["presence_penalty"],
    )
    cache = model.make_cache()
    ids = _prompt_ids(prov)
    model(mx.array(ids[:-1])[None], cache=cache)
    mx.eval([c.state for c in cache])
    token, out = ids[-1], []
    for _ in range(n):
        logits = model(mx.array([token])[None], cache=cache)[:, -1, :].astype(mx.float32)
        logprobs = logits - mx.logsumexp(logits, axis=-1, keepdims=True)
        mx.eval(logprobs)
        chosen = int(sampler(np.array(logprobs).reshape(-1)))
        if chosen in eos:
            break
        out.append(chosen)
        token = chosen
    return out


def test_capture_does_not_change_the_generated_tokens(provider) -> None:  # type: ignore[no-untyped-def]
    from sensos_inference.providers.qwen35_mlx_capture import PILOT_POSITIONS

    n = 160
    result = provider.capture_chat(MESSAGES, positions=PILOT_POSITIONS, max_tokens=n, **SAMPLING)
    assert result.token_ids == _reference_tokens(provider, n)
    assert set(result.states) == {p.name for p in PILOT_POSITIONS}
    for arr in result.states.values():
        assert arr.shape == (len(result.token_ids), 1024) and arr.dtype == np.float32
        assert np.all(np.isfinite(arr))
    # a second capture with fewer positions gives the same tokens and the same shared states
    one = provider.capture_chat(MESSAGES, positions=PILOT_POSITIONS[-1:], max_tokens=n, **SAMPLING)
    assert one.token_ids == result.token_ids
    assert np.array_equal(one.states["final_norm"], result.states["final_norm"])


def test_same_seed_twice_is_identical(provider) -> None:  # type: ignore[no-untyped-def]
    a = provider.capture_chat(MESSAGES, max_tokens=64, **SAMPLING)
    b = provider.capture_chat(MESSAGES, max_tokens=64, **SAMPLING)
    assert a.token_ids == b.token_ids
    assert all(np.array_equal(a.states[k], b.states[k]) for k in a.states)
