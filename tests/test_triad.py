"""
Tests for the SPEC-SENSOS-RTV2-001 v1.4 Section 2.1 Canonical State Triad
pure functions. All inputs are synthetic numeric matrices/arrays used to
verify arithmetic correctness — none represent a real observation,
trajectory, or hidden state.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from sensos.triad import (
    SpecificationDecisionRequired,
    canonical_variance,
    normalized_eigenvalues,
    normalized_spectral_entropy,
    raw_spectral_entropy,
)

# ---------------------------------------------------------------------------
# canonical_variance
# ---------------------------------------------------------------------------


def test_variance_identity_covariance():
    assert canonical_variance(np.eye(4)) == pytest.approx(4.0)


def test_variance_diagonal_covariance():
    assert canonical_variance(np.diag([1.0, 2.0, 3.0])) == pytest.approx(6.0)


def test_variance_zero_covariance():
    # trace of the zero matrix is a legitimate, well-defined answer (0.0),
    # unlike entropy over an all-zero eigenvalue spectrum, which is
    # undefined (see test_normalized_eigenvalues_zero_sum_raises).
    assert canonical_variance(np.zeros((3, 3))) == pytest.approx(0.0)


def test_variance_known_eigenvalue_distribution():
    # A diagonal matrix's eigenvalues ARE its diagonal entries.
    cov = np.diag([5.0, 0.0, 2.5])
    assert canonical_variance(cov) == pytest.approx(7.5)


def test_variance_dimension_mismatch_non_square_raises():
    with pytest.raises(ValueError, match="square"):
        canonical_variance(np.ones((2, 3)))


def test_variance_dimension_mismatch_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        canonical_variance(np.zeros((0, 0)))


def test_variance_non_symmetric_raises():
    with pytest.raises(ValueError, match="symmetric"):
        canonical_variance(np.array([[1.0, 2.0], [0.0, 1.0]]))


def test_variance_invalid_negative_eigenvalue_raises():
    # [[1, 2], [2, 1]] is symmetric with eigenvalues {3, -1} -- not a valid
    # covariance matrix (not positive-semi-definite).
    with pytest.raises(ValueError, match="positive-semi-definite"):
        canonical_variance(np.array([[1.0, 2.0], [2.0, 1.0]]))


# ---------------------------------------------------------------------------
# normalized_eigenvalues
# ---------------------------------------------------------------------------


def test_normalized_eigenvalues_sums_to_one():
    result = normalized_eigenvalues([1.0, 2.0, 3.0, 4.0])
    assert result.sum() == pytest.approx(1.0)
    assert result.tolist() == pytest.approx([0.1, 0.2, 0.3, 0.4])


def test_normalized_eigenvalues_negative_raises():
    with pytest.raises(ValueError, match="non-negative"):
        normalized_eigenvalues([1.0, -0.5, 2.0])


def test_normalized_eigenvalues_zero_sum_raises():
    with pytest.raises(ValueError, match="undefined"):
        normalized_eigenvalues([0.0, 0.0, 0.0])


def test_normalized_eigenvalues_empty_raises():
    with pytest.raises(ValueError, match="non-empty"):
        normalized_eigenvalues([])


def test_normalized_eigenvalues_dimension_mismatch_raises():
    with pytest.raises(ValueError, match="1D"):
        normalized_eigenvalues([[1.0, 2.0], [3.0, 4.0]])


# ---------------------------------------------------------------------------
# raw_spectral_entropy
# ---------------------------------------------------------------------------


def test_raw_entropy_uniform_distribution_is_maximal():
    # d equal eigenvalues -> maximum-entropy distribution -> H = ln(d).
    assert raw_spectral_entropy([1.0, 1.0, 1.0, 1.0]) == pytest.approx(math.log(4))


def test_raw_entropy_single_dominant_eigenvalue_is_zero():
    # A single nonzero eigenvalue is a fully-determined (zero-entropy)
    # spectrum. Also exercises the 0 * ln(0) = 0 numerical-stability
    # convention for the zero-valued eigenvalues.
    assert raw_spectral_entropy([1.0, 0.0, 0.0, 0.0]) == pytest.approx(0.0, abs=1e-12)


def test_raw_entropy_known_two_state_distribution():
    # lambda~ = [0.5, 0.5] -> H = ln(2), the standard two-outcome maximum.
    assert raw_spectral_entropy([1.0, 1.0]) == pytest.approx(math.log(2))


def test_raw_entropy_numerical_stability_many_near_zero_terms():
    # Many tiny-but-nonzero eigenvalues alongside one dominant one must not
    # produce NaN/inf from log(~0).
    eigenvalues = [1000.0] + [1e-300] * 50
    result = raw_spectral_entropy(eigenvalues)
    assert math.isfinite(result)
    assert result >= 0.0


def test_raw_entropy_bounded_by_log_d():
    eigenvalues = [3.0, 1.0, 0.5, 7.0, 2.0]
    d = len(eigenvalues)
    result = raw_spectral_entropy(eigenvalues)
    assert 0.0 - 1e-9 <= result <= math.log(d) + 1e-9


def test_raw_entropy_zero_eigenvalues_raises():
    with pytest.raises(ValueError, match="undefined"):
        raw_spectral_entropy([0.0, 0.0])


# ---------------------------------------------------------------------------
# normalized_spectral_entropy — deliberately unimplemented
# ---------------------------------------------------------------------------


def test_normalized_entropy_raises_specification_decision_required():
    with pytest.raises(SpecificationDecisionRequired, match="0,1"):
        normalized_spectral_entropy([1.0, 1.0, 1.0])
