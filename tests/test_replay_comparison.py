"""
Tests for sensos.replay_comparison (SPEC-SENSOS-RTV2-001 v1.4 Section 7.4
G0-A/G0-B). All arrays below are synthetic — no real EOU replay exists yet.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest
from sensos.parameter_registry import DEFAULT as PARAMETER_REGISTRY
from sensos.replay_comparison import (
    bit_exact_match,
    cross_attestation_match,
    max_norm_distance,
)

# ---------------------------------------------------------------------------
# bit_exact_match (G0-A)
# ---------------------------------------------------------------------------


def test_identical_arrays_are_bit_exact():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0, 3.0])
    assert bit_exact_match(a, b) is True


def test_tiny_float_difference_is_not_bit_exact():
    a = np.array([1.0])
    # smallest possible float64 increment above 1.0 -- guaranteed to be a
    # genuinely different bit pattern, however numerically tiny.
    b = np.array([np.nextafter(1.0, 2.0)])
    assert bit_exact_match(a, b) is False


def test_different_shape_is_not_bit_exact():
    assert bit_exact_match(np.array([1.0, 2.0]), np.array([1.0, 2.0, 3.0])) is False


def test_different_dtype_is_not_bit_exact():
    a = np.array([1.0], dtype=np.float32)
    b = np.array([1.0], dtype=np.float64)
    assert bit_exact_match(a, b) is False


def test_negative_zero_vs_positive_zero_not_bit_exact():
    # Numerically equal under ==, but a different bit pattern -- this is
    # exactly why byte comparison is used instead of np.array_equal.
    a = np.array([0.0])
    b = np.array([-0.0])
    assert a[0] == b[0]  # sanity: numerically "equal"
    assert bit_exact_match(a, b) is False  # but not bit-exact


def test_identical_nan_bit_patterns_are_bit_exact():
    a = np.array([float("nan"), 1.0])
    b = np.array([float("nan"), 1.0])
    # under normal `==`, nan != nan -- but identical NaN bit patterns
    # (both from float("nan")) ARE byte-identical.
    assert bit_exact_match(a, b) is True


def test_self_comparison_is_bit_exact():
    a = np.array([1.0, 2.0, 3.0])
    assert bit_exact_match(a, a) is True


# ---------------------------------------------------------------------------
# max_norm_distance / cross_attestation_match (G0-B)
# ---------------------------------------------------------------------------


def test_max_norm_distance_known_value():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.5, 2.0])
    # |diffs| = [0, 0.5, 1.0] -> max = 1.0
    assert max_norm_distance(a, b) == pytest.approx(1.0)


def test_max_norm_distance_shape_mismatch_raises():
    with pytest.raises(ValueError, match="shape mismatch"):
        max_norm_distance(np.array([1.0, 2.0]), np.array([1.0, 2.0, 3.0]))


def test_max_norm_distance_zero_for_identical_arrays():
    a = np.array([1.0, 2.0, 3.0])
    assert max_norm_distance(a, a) == pytest.approx(0.0)


def test_default_epsilon_matches_parameter_registry():
    default_epsilon = inspect.signature(cross_attestation_match).parameters["epsilon"].default
    assert default_epsilon == PARAMETER_REGISTRY.CROSS_HARDWARE_EPSILON == 1e-4


def test_distance_within_epsilon_matches():
    a = np.array([1.0, 2.0, 3.0])
    b = a + 1e-5  # well within default 1e-4
    assert cross_attestation_match(a, b) is True


def test_distance_exactly_at_epsilon_matches():
    a = np.array([1.0])
    b = np.array([1.0 + 1e-4])
    assert cross_attestation_match(a, b, epsilon=1e-4) is True


def test_distance_just_above_epsilon_does_not_match():
    a = np.array([1.0])
    b = np.array([1.0 + 1.001e-4])
    assert cross_attestation_match(a, b, epsilon=1e-4) is False


def test_distance_far_beyond_epsilon_does_not_match():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0, 30.0])
    assert cross_attestation_match(a, b) is False


def test_bit_exact_implies_cross_attestation_match():
    # Anything that passes the strict G0-A bar must also pass the looser
    # G0-B bar (distance 0 <= any positive epsilon).
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0, 3.0])
    assert bit_exact_match(a, b) is True
    assert cross_attestation_match(a, b) is True
