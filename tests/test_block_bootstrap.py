"""
Tests for sensos.block_bootstrap (SPEC-SENSOS-RTV2-001 v1.4 Section 7.3).
All cluster data below is synthetic — none represents real seed-cluster
Port observations.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest
from sensos.block_bootstrap import block_bootstrap, flatten_resample


def _synthetic_clusters(n_clusters=10, cluster_size=7, seed=42):
    rng = np.random.default_rng(seed)
    return {f"seed_{k}": rng.normal(loc=k, scale=1.0, size=cluster_size).tolist() for k in range(n_clusters)}


def _mean_statistic(resample):
    return float(np.mean(flatten_resample(resample)))


def test_required_kwargs_have_no_defaults():
    # v1.4 Section 7.3 gives no iteration count or seed -- this must not be
    # silently defaulted (see module docstring).
    sig = inspect.signature(block_bootstrap)
    assert sig.parameters["n_iterations"].default is inspect.Parameter.empty
    assert sig.parameters["rng_seed"].default is inspect.Parameter.empty


def test_deterministic_given_same_seed():
    data = _synthetic_clusters()
    r1 = block_bootstrap(data, _mean_statistic, n_iterations=50, rng_seed=7)
    r2 = block_bootstrap(data, _mean_statistic, n_iterations=50, rng_seed=7)
    assert np.array_equal(r1, r2)


def test_different_seeds_generally_differ():
    data = _synthetic_clusters()
    r1 = block_bootstrap(data, _mean_statistic, n_iterations=50, rng_seed=1)
    r2 = block_bootstrap(data, _mean_statistic, n_iterations=50, rng_seed=2)
    assert not np.array_equal(r1, r2)


def test_statistic_fn_called_exactly_n_iterations_times():
    data = _synthetic_clusters()
    call_count = 0

    def counting_statistic(resample):
        nonlocal call_count
        call_count += 1
        return 0.0

    block_bootstrap(data, counting_statistic, n_iterations=17, rng_seed=1)
    assert call_count == 17


def test_result_length_matches_n_iterations():
    data = _synthetic_clusters()
    result = block_bootstrap(data, _mean_statistic, n_iterations=30, rng_seed=1)
    assert len(result) == 30


def test_non_positive_n_iterations_raises():
    data = _synthetic_clusters()
    with pytest.raises(ValueError, match="n_iterations"):
        block_bootstrap(data, _mean_statistic, n_iterations=0, rng_seed=1)


def test_empty_data_raises():
    with pytest.raises(ValueError, match="at least one cluster"):
        block_bootstrap({}, _mean_statistic, n_iterations=5, rng_seed=1)


def test_resampled_clusters_stay_intact_blocks():
    # Each drawn cluster's original value sequence must appear whole and
    # unsplit in the resample -- this is what distinguishes a BLOCK
    # bootstrap from resampling individual observations.
    data = {"seed_0": [1.0, 2.0, 3.0], "seed_1": [10.0, 20.0, 30.0]}

    captured = []

    def capture_resample(resample):
        captured.append(resample)
        return 0.0

    block_bootstrap(data, capture_resample, n_iterations=5, rng_seed=3)

    for resample in captured:
        assert len(resample) == 2  # n_clusters draws each iteration
        for cluster_id, values in resample:
            assert list(values) == data[cluster_id]  # block never split/reordered


def test_drawn_cluster_can_repeat_with_replacement():
    # With only 2 clusters and enough iterations, at least one resample
    # should draw the same cluster twice (with replacement).
    data = {"seed_0": [1.0], "seed_1": [2.0]}
    saw_duplicate = False
    for iteration_seed in range(20):
        captured = []
        block_bootstrap(
            data,
            lambda resample, _captured=captured: _captured.append(resample) or 0.0,
            n_iterations=1,
            rng_seed=iteration_seed,
        )
        cluster_ids_drawn = [cid for cid, _ in captured[0]]
        if len(set(cluster_ids_drawn)) < len(cluster_ids_drawn):
            saw_duplicate = True
            break
    assert saw_duplicate


def test_flatten_resample_preserves_duplication():
    resample = [("seed_0", [1.0, 2.0]), ("seed_0", [1.0, 2.0]), ("seed_1", [9.0])]
    flat = flatten_resample(resample)
    assert flat == [1.0, 2.0, 1.0, 2.0, 9.0]
