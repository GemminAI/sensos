"""
Tests for sensos.permutation (SPEC-SENSOS-RTV2-001 v1.4 Section 7.4 G2).
All data below is synthetic — none represents a real Port/Attribution
observation.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest
from sensos.permutation import permutation_null_distribution, permutation_pvalue


def test_required_kwargs_have_no_defaults():
    sig1 = inspect.signature(permutation_null_distribution)
    assert sig1.parameters["n_permutations"].default is inspect.Parameter.empty
    assert sig1.parameters["rng_seed"].default is inspect.Parameter.empty

    sig2 = inspect.signature(permutation_pvalue)
    assert sig2.parameters["alternative"].default is inspect.Parameter.empty


# ---------------------------------------------------------------------------
# permutation_null_distribution
# ---------------------------------------------------------------------------


def _identity_statistic(data):
    return float(np.sum(data))


def _shuffle_permute(data, rng):
    return rng.permutation(data)


def test_deterministic_given_same_seed():
    data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    r1 = permutation_null_distribution(data, _identity_statistic, _shuffle_permute, n_permutations=50, rng_seed=7)
    r2 = permutation_null_distribution(data, _identity_statistic, _shuffle_permute, n_permutations=50, rng_seed=7)
    assert np.array_equal(r1, r2)


def test_shuffle_invariant_statistic_is_constant_null():
    # sum() is invariant to permutation, so every null value equals the
    # observed sum -- a strong mechanical sanity check.
    data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    null = permutation_null_distribution(data, _identity_statistic, _shuffle_permute, n_permutations=20, rng_seed=1)
    assert np.allclose(null, 15.0)


def test_statistic_fn_called_exactly_n_permutations_times():
    call_count = 0

    def counting_statistic(data):
        nonlocal call_count
        call_count += 1
        return 0.0

    permutation_null_distribution(
        np.array([1.0, 2.0]), counting_statistic, _shuffle_permute, n_permutations=13, rng_seed=1
    )
    assert call_count == 13


def test_result_length_matches_n_permutations():
    data = np.array([1.0, 2.0, 3.0])
    result = permutation_null_distribution(data, _identity_statistic, _shuffle_permute, n_permutations=25, rng_seed=1)
    assert len(result) == 25


def test_non_positive_n_permutations_raises():
    with pytest.raises(ValueError, match="n_permutations"):
        permutation_null_distribution(np.array([1.0]), _identity_statistic, _shuffle_permute, n_permutations=0, rng_seed=1)


# ---------------------------------------------------------------------------
# permutation_pvalue
# ---------------------------------------------------------------------------


def test_invalid_alternative_raises():
    with pytest.raises(ValueError, match="alternative"):
        permutation_pvalue(1.0, np.array([0.1, 0.2, 0.3]), alternative="sideways")


def test_empty_null_distribution_raises():
    with pytest.raises(ValueError, match="non-empty"):
        permutation_pvalue(1.0, np.array([]), alternative="greater")


def test_observed_far_above_null_gives_minimal_pvalue_greater():
    null = np.array([0.1, 0.2, 0.15, 0.05, 0.3] * 20)  # 100 values, all << 100
    p = permutation_pvalue(100.0, null, alternative="greater")
    assert p == pytest.approx(1.0 / 101)  # add-one correction: 0 exceed + 1, over n+1


def test_observed_far_below_null_gives_maximal_pvalue_greater():
    null = np.array([10.0, 20.0, 15.0] * 10)  # 30 values, all >> observed
    p = permutation_pvalue(0.0, null, alternative="greater")
    assert p == pytest.approx(1.0)  # every null value exceeds observed


def test_less_alternative_is_mirror_of_greater():
    null = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    p_greater_low_observed = permutation_pvalue(0.0, null, alternative="greater")
    p_less_low_observed = permutation_pvalue(0.0, null, alternative="less")
    assert p_greater_low_observed == pytest.approx(1.0)
    assert p_less_low_observed == pytest.approx(1.0 / 6)  # only 0.0 itself would count, none <= 0.0 here


def test_two_sided_uses_absolute_value():
    null = np.array([-5.0, -1.0, 1.0, 5.0])
    p_pos = permutation_pvalue(4.0, null, alternative="two-sided")
    p_neg = permutation_pvalue(-4.0, null, alternative="two-sided")
    assert p_pos == pytest.approx(p_neg)  # symmetric under sign flip


def test_pvalue_always_in_valid_range():
    null = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    for observed in [-10.0, 0.0, 2.5, 100.0]:
        for alt in ["greater", "less", "two-sided"]:
            p = permutation_pvalue(observed, null, alternative=alt)
            assert 0.0 < p <= 1.0


# ---------------------------------------------------------------------------
# End-to-end: label-shuffle permutation test on synthetic two-group data
# ---------------------------------------------------------------------------


def test_end_to_end_label_shuffle_detects_planted_effect():
    rng = np.random.default_rng(123)
    group_a = rng.normal(loc=10.0, scale=1.0, size=30)
    group_b = rng.normal(loc=0.0, scale=1.0, size=30)
    values = np.concatenate([group_a, group_b])
    labels = np.array([0] * 30 + [1] * 30)
    observed = float(values[labels == 0].mean() - values[labels == 1].mean())

    def statistic_fn(permuted_labels):
        return float(values[permuted_labels == 0].mean() - values[permuted_labels == 1].mean())

    def permute_fn(_data, rng_):
        return rng_.permutation(labels)

    null = permutation_null_distribution(labels, statistic_fn, permute_fn, n_permutations=500, rng_seed=42)
    p = permutation_pvalue(observed, null, alternative="greater")
    # A ~10-standard-deviation planted mean difference should never be
    # matched by any label shuffle -> minimal add-one p-value.
    assert p == pytest.approx(1.0 / 501)
