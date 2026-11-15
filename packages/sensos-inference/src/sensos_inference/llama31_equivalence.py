"""Bit comparison of the Llama capture path with the model's own call (U2, design section 5).

Kept out of ``adapters.py`` on purpose: that module must not import MLX (test T-U2-P-09). This one
imports MLX inside the function only, so importing it needs no MLX. Reached through
``Llama31MLXAdapter.check_equivalence``. The provider is not changed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def llama31_equivalence_check(
    provider: Any,
    prompt_ids: Sequence[int],
    token_ids: Sequence[int],
    *,
    chunk: int = 2048,
    boundary: int = 8,
    tail: int = 48,
    steps: int = 32,
) -> dict[str, Any]:
    """Bit-compare the capture path with the model's own call, chunked like the capture prefill.

    Capture path: ``model.model(chunk, cache)`` over the prompt without its last token in chunks of
    ``chunk`` tokens (what ``MLXEngine.prefill`` does; its cache is also compared), then
    ``MLXEngine.step`` for ``steps`` tokens. Reference: ``model(chunk, cache)`` over the same
    chunks with a new cache, then ``model(token, cache)`` per step; its final-norm output is read
    by tapping ``model.model.norm``. Compared bit for bit, no tolerance: the logits and the
    final-norm output around every chunk boundary (``boundary`` positions on each side) and at the
    last ``tail`` positions of the prefill, and the log-probabilities and state of each step.

    Needs MLX and a loaded provider (imports lazily; the provider is not changed).
    ``bit_identical`` is True only when every difference is exactly 0.0 and the cache the replica
    built equals the cache of ``MLXEngine.prefill``.
    """
    import mlx.core as mx
    import mlx.nn as nn
    import numpy as np
    from mlx_lm.models.cache import make_prompt_cache

    from sensos_inference.providers.llama31_mlx_capture import MLXEngine

    model = provider._model
    inner = model.model

    class _Tap(nn.Module):  # type: ignore[misc]
        def __init__(self, wrapped: Any) -> None:
            super().__init__()
            self.wrapped = wrapped
            self.last: Any = None

        def __call__(self, x: Any) -> Any:
            self.last = self.wrapped(x)
            return self.last

    def logits_of(hidden: Any) -> Any:  # the expression of MLXEngine.step / Model.__call__
        if model.args.tie_word_embeddings:
            return inner.embed_tokens.as_linear(hidden)
        return model.lm_head(hidden)

    def f32(array: Any) -> Any:
        return np.array(array.astype(mx.float32))

    def worst(a: Any, b: Any) -> float:
        return float(np.max(np.abs(f32(a) - f32(b)))) if a.size else 0.0

    head = [int(i) for i in prompt_ids[:-1]]
    boundaries = list(range(chunk, len(head), chunk))
    wanted: set[int] = set()
    for edge in boundaries:
        wanted.update(range(max(edge - boundary, 0), min(edge + boundary, len(head))))
    wanted.update(range(max(len(head) - tail, 0), len(head)))

    original_norm = inner.norm
    tap = _Tap(original_norm)
    max_hidden = max_logit = 0.0
    where: dict[str, Any] = {"hidden": None, "logits": None}
    compared = 0
    engine = MLXEngine(model)
    replica = make_prompt_cache(model)
    reference = make_prompt_cache(model)
    try:
        inner.norm = tap
        start = 0
        while start < len(head):
            piece = mx.array(head[start : start + chunk])[None]
            mine = inner(piece, cache=replica)
            theirs_logits = model(piece, cache=reference)
            theirs_hidden = tap.last
            mx.eval(mine, theirs_logits, theirs_hidden)
            local = [p - start for p in sorted(wanted) if start <= p < start + piece.shape[1]]
            if local:
                index = mx.array(local)
                # lm_head over the whole chunk, as model(...) does, then pick the positions: a
                # product over a different number of rows need not be bit-identical.
                mine_logits = logits_of(mine)
                diff_h = worst(mine[:, index, :], theirs_hidden[:, index, :])
                diff_l = worst(mine_logits[:, index, :], theirs_logits[:, index, :])
                compared += len(local)
                if diff_h > max_hidden:
                    max_hidden, where["hidden"] = diff_h, start + local[0]
                if diff_l > max_logit:
                    max_logit, where["logits"] = diff_l, start + local[0]
            start += chunk
            mx.eval([c.state for c in replica], [c.state for c in reference])
            mx.clear_cache()
        if head:
            engine.prefill(head)
        cache_equal = all(
            bool(mx.array_equal(a, b))
            for ca, cb in zip(engine._cache, replica, strict=True)
            for a, b in zip(ca.state, cb.state, strict=True)
        )
        feed = [int(prompt_ids[-1]), *[int(t) for t in token_ids]][:steps]
        max_logprob = max_state = 0.0
        for token in feed:
            logprobs, state = engine.step(token)
            out = model(mx.array([token])[None], cache=reference)[:, -1, :]
            ref_logprobs = out - mx.logsumexp(out, keepdims=True)
            ref_state = tap.last[0, -1, :]
            mx.eval(ref_logprobs, ref_state)
            d_logprob = np.abs(logprobs - f32(ref_logprobs).reshape(-1))
            d_state = np.abs(state - f32(ref_state).reshape(-1))
            max_logprob = max(max_logprob, float(d_logprob.max()))
            max_state = max(max_state, float(d_state.max()))
    finally:
        inner.norm = original_norm
    exact = max_hidden == max_logit == max_logprob == max_state == 0.0 and cache_equal
    return {
        "chunk": chunk,
        "prefill_tokens": len(head),
        "chunk_boundaries": boundaries,
        "positions_compared": compared,
        "boundary_positions_each_side": boundary,
        "tail_positions": tail,
        "max_abs_hidden_diff": max_hidden,
        "max_abs_logit_diff": max_logit,
        "worst_position": where,
        "cache_equal_after_prefill": cache_equal,
        "steps": len(feed),
        "max_abs_logprob_diff": max_logprob,
        "max_abs_state_diff": max_state,
        "bit_identical": exact,
    }


__all__ = ["llama31_equivalence_check"]
