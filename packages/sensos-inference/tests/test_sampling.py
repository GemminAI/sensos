"""``warp_logits`` against a line-by-line NumPy port of the Hugging Face transformers v4.48.3 warpers
(``generation/logits_process.py``, sha256 8b0af084f08813528217d3854728939cb13fe15f1c7b6f674672e016eabbc3a1,
``TemperatureLogitsWarper`` / ``TopKLogitsWarper`` / ``TopPLogitsWarper`` ``__call__`` bodies) and the
processor order of ``generation/utils.py`` (temperature, top_k, top_p).
"""

import numpy as np
import pytest

from sensos_inference.sampling import HFOrderSampler, probabilities, warp_logits


def hf_reference(scores, temperature, top_k, top_p):
    scores = np.asarray(scores, dtype=np.float64).copy()
    if temperature is not None and temperature != 1.0:
        scores = scores / temperature  # TemperatureLogitsWarper
    if top_k is not None and top_k != 0:  # TopKLogitsWarper
        k = min(top_k, scores.shape[-1])
        topk_last = np.sort(scores)[::-1][k - 1]
        scores = np.where(scores < topk_last, -np.inf, scores)
    if top_p is not None and top_p < 1.0:  # TopPLogitsWarper
        order = np.argsort(scores, kind="stable")
        sorted_logits = scores[order]
        e = np.exp(sorted_logits - sorted_logits.max())
        cumulative = np.cumsum(e / e.sum())
        remove_sorted = cumulative <= (1 - top_p)
        remove_sorted[-1:] = False  # min_tokens_to_keep = 1
        remove = np.zeros_like(remove_sorted)
        remove[order] = remove_sorted
        scores = np.where(remove, -np.inf, scores)
    return scores


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("params", [(0.7, 50, 0.95), (0.7, 3, 0.95), (1.0, 0, 0.5), (0.3, 5, 0.9), (0.7, 0, 1.0)])
def test_matches_hf_reference(seed, params):
    rng = np.random.default_rng(seed)
    logits = rng.normal(0, 3, size=64)
    t, k, p = params
    ours = warp_logits(logits, temperature=t, top_k=k, top_p=p)
    ref = hf_reference(logits, t, k, p)
    assert np.array_equal(np.isfinite(ours), np.isfinite(ref))
    np.testing.assert_allclose(probabilities(ours), probabilities(ref), rtol=0, atol=1e-15)


def test_order_is_temperature_then_top_k_then_top_p():
    logits = np.array([2.0, 1.0, 0.9, 0.8, 0.7, 0.6])
    # top_p computed on the temperature-scaled distribution (HF), not on T=1 (mlx_lm)
    hf = warp_logits(logits, temperature=0.5, top_k=0, top_p=0.9)
    t1 = warp_logits(logits, temperature=1.0, top_k=0, top_p=0.9) / 1.0
    assert np.isfinite(hf).sum() == 4 and np.isfinite(t1).sum() == 5


def test_min_tokens_to_keep_and_ties():
    logits = np.array([5.0, 5.0, 5.0, 0.0])
    out = warp_logits(logits, temperature=1.0, top_k=2, top_p=1.0)
    assert np.isfinite(out).sum() == 3  # ties with the k-th value are kept (HF: `<`)
    out = warp_logits(np.array([10.0, 0, 0, 0]), temperature=1.0, top_k=0, top_p=0.01)
    assert np.isfinite(out).sum() == 1


def test_sampler_empirical_distribution_and_determinism():
    logits = np.log(np.array([0.5, 0.3, 0.15, 0.05]))
    s = HFOrderSampler(temperature=1.0, top_k=0, top_p=0.9, seed=1)
    draws = np.array([s(logits) for _ in range(4000)])
    assert set(draws) <= {0, 1, 2}  # 0.05 token is removed by top_p (cum 0.05 <= 0.1)
    expected = probabilities(warp_logits(logits, temperature=1.0, top_k=0, top_p=0.9))
    freq = np.bincount(draws, minlength=4) / len(draws)
    np.testing.assert_allclose(freq, expected, atol=0.03)
    a = [HFOrderSampler(temperature=0.7, top_k=50, top_p=0.95, seed=5)(logits) for _ in range(1)]
    b = [HFOrderSampler(temperature=0.7, top_k=50, top_p=0.95, seed=5)(logits) for _ in range(1)]
    assert a == b
