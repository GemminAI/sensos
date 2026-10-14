"""Sampler with the arithmetic and order of Hugging Face transformers 4.48.3 ``generate``.

Order (``generation/utils.py::_get_logits_processor``): temperature (if not None and != 1.0) -> top_k
(if not None and != 0) -> top_p (if not None and < 1.0). Warpers (``generation/logits_process.py``):

* temperature: ``scores / temperature``
* top_k: ``scores < topk(scores, k)[0][-1]`` -> ``-inf`` (ties with the k-th value are kept)
* top_p: sort ascending, ``cumsum(softmax(sorted))``, remove where ``cum <= 1 - top_p``, never remove
  the last ``min_tokens_to_keep`` of the sorted order (the most probable tokens)

The draw is ``softmax`` of the filtered scores and a categorical sample from NumPy's ``Generator``
(``PCG64``), seeded by the caller. torch's multinomial is not reproduced.
"""

from __future__ import annotations

import numpy as np

NEG_INF = -np.inf


def warp_logits(
    logits: np.ndarray,
    *,
    temperature: float | None = 1.0,
    top_k: int | None = 0,
    top_p: float | None = 1.0,
    min_tokens_to_keep: int = 1,
) -> np.ndarray:
    scores = np.asarray(logits, dtype=np.float64).copy()
    if scores.ndim != 1:
        raise ValueError("logits must be a 1-D vector")
    if temperature is not None and temperature != 1.0:
        scores = scores / temperature
    if top_k is not None and top_k != 0:
        k = min(top_k, scores.shape[-1])
        kth = np.sort(scores)[::-1][k - 1]  # the k-th largest value
        scores = np.where(scores < kth, NEG_INF, scores)
    if top_p is not None and top_p < 1.0:
        order = np.argsort(scores, kind="stable")  # ascending
        sorted_scores = scores[order]
        finite = np.where(np.isfinite(sorted_scores), sorted_scores, -np.inf)
        shifted = finite - np.max(finite)
        probs = np.exp(shifted)
        probs = probs / probs.sum()
        cumulative = np.cumsum(probs)
        remove_sorted = cumulative <= (1.0 - top_p)
        if min_tokens_to_keep > 0:
            remove_sorted[-min_tokens_to_keep:] = False
        remove = np.zeros_like(remove_sorted)
        remove[order] = remove_sorted
        scores = np.where(remove, NEG_INF, scores)
    return scores


def probabilities(scores: np.ndarray) -> np.ndarray:
    finite_max = np.max(scores[np.isfinite(scores)])
    expd = np.exp(scores - finite_max)
    expd[~np.isfinite(scores)] = 0.0
    return expd / expd.sum()


class HFOrderSampler:
    """Callable ``sampler(logprobs) -> token id`` for ``mlx_lm.stream_generate(sampler=...)``.

    ``logprobs`` may be an mlx array (anything ``np.asarray`` accepts); ``log_softmax`` of logits and
    logits differ only by a constant per row, so the warpers (shift-invariant after the temperature
    division is applied to the *logits*) are applied to ``logprobs / temperature`` -- equal to
    ``logits / temperature`` up to an additive constant, which no warper depends on.
    """

    def __init__(self, *, temperature: float, top_k: int, top_p: float, seed: int) -> None:
        self.temperature, self.top_k, self.top_p, self.seed = temperature, top_k, top_p, seed
        self._rng = np.random.Generator(np.random.PCG64(seed))

    def settings(self) -> dict[str, object]:
        return {
            "order": ["temperature", "top_k", "top_p"],
            "temperature": self.temperature,
            "top_k": self.top_k,
            "top_p": self.top_p,
            "min_tokens_to_keep": 1,
            "seed": self.seed,
            "rng": "numpy.random.PCG64",
            "reference": "transformers 4.48.3 generation/logits_process.py + generation/utils.py",
        }

    def __call__(self, logprobs: object) -> int:
        row = np.asarray(logprobs, dtype=np.float64).reshape(-1)
        scores = warp_logits(
            row, temperature=self.temperature, top_k=self.top_k, top_p=self.top_p
        )
        p = probabilities(scores)
        return int(self._rng.choice(p.shape[0], p=p))
