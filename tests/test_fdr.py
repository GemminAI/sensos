"""
Tests for sensos.fdr (SPEC-SENSOS-RTV2-001 v1.4 Section 7.1/7.4). Cross-
validated against SciPy's independent ``false_discovery_control``
implementation on many synthetic p-value sets — not merely self-
consistency — the same standard applied to the RFC 8785 vectors in
test_canonical_hash.py.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import false_discovery_control
from sensos.fdr import benjamini_hochberg_adjusted_pvalues, benjamini_hochberg_reject
from sensos.parameter_registry import DEFAULT as PARAMETER_REGISTRY

# ---------------------------------------------------------------------------
# Cross-validation against SciPy (authoritative external reference)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size,seed", [(5, 0), (10, 1), (25, 2), (100, 3), (2, 4)])
def test_matches_scipy_false_discovery_control(size, seed):
    rng = np.random.default_rng(seed)
    p_values = rng.uniform(0.0, 1.0, size=size)
    ours = benjamini_hochberg_adjusted_pvalues(p_values)
    theirs = false_discovery_control(p_values, method="bh")
    assert ours == pytest.approx(theirs, abs=1e-9)


def test_matches_scipy_with_tied_pvalues():
    p_values = np.array([0.01, 0.01, 0.05, 0.05, 0.5, 0.9])
    ours = benjamini_hochberg_adjusted_pvalues(p_values)
    theirs = false_discovery_control(p_values, method="bh")
    assert ours == pytest.approx(theirs, abs=1e-9)


def test_hand_verifiable_small_example():
    # m=4, p = [0.01, 0.04, 0.03, 0.20]; sorted: 0.01(rank1), 0.03(rank2),
    # 0.04(rank3), 0.20(rank4). raw adjusted = p*m/rank:
    #   0.01*4/1=0.04, 0.03*4/2=0.06, 0.04*4/3=0.0533.., 0.20*4/4=0.20
    # monotone (running min from the back): [0.04, 0.0533.., 0.0533.., 0.20]
    p_values = np.array([0.01, 0.04, 0.03, 0.20])
    adjusted = benjamini_hochberg_adjusted_pvalues(p_values)
    expected = np.array([0.04, 0.04 * 4 / 3, 0.04 * 4 / 3, 0.20])
    assert adjusted == pytest.approx(expected, abs=1e-9)


# ---------------------------------------------------------------------------
# benjamini_hochberg_reject
# ---------------------------------------------------------------------------


def test_default_q_matches_parameter_registry():
    import inspect

    default_q = inspect.signature(benjamini_hochberg_reject).parameters["q"].default
    assert default_q == PARAMETER_REGISTRY.FDR_BENJAMINI_HOCHBERG_Q == 0.05


def test_all_significant_pvalues_all_rejected():
    p_values = np.array([0.0001, 0.0002, 0.0003])
    assert np.all(benjamini_hochberg_reject(p_values, q=0.05))


def test_all_insignificant_pvalues_none_rejected():
    p_values = np.array([0.9, 0.95, 0.99])
    assert not np.any(benjamini_hochberg_reject(p_values, q=0.05))


def test_reject_order_matches_input_order():
    p_values = np.array([0.9, 0.0001, 0.5])
    rejected = benjamini_hochberg_reject(p_values, q=0.05)
    assert rejected[1]  # the smallest p-value, at index 1
    assert not rejected[0]
    assert not rejected[2]


def test_q_out_of_range_raises():
    with pytest.raises(ValueError, match="q must be"):
        benjamini_hochberg_reject(np.array([0.1, 0.2]), q=1.5)
    with pytest.raises(ValueError, match="q must be"):
        benjamini_hochberg_reject(np.array([0.1, 0.2]), q=0.0)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_empty_pvalues_raises():
    with pytest.raises(ValueError, match="non-empty"):
        benjamini_hochberg_adjusted_pvalues(np.array([]))


def test_out_of_range_pvalue_raises():
    with pytest.raises(ValueError, match="\\[0, 1\\]"):
        benjamini_hochberg_adjusted_pvalues(np.array([0.5, 1.2]))


def test_negative_pvalue_raises():
    with pytest.raises(ValueError, match="\\[0, 1\\]"):
        benjamini_hochberg_adjusted_pvalues(np.array([0.5, -0.1]))
