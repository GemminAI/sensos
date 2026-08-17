"""
Tests for sensos.standardization (SPEC-SENSOS-RTV2-001 v1.4 Section 5.2).
All pools/values below are synthetic numeric arrays — none represent a
real Stateless-pool observation.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from sensos.standardization import zscore, zscore_array


def test_zscore_known_value():
    assert zscore(5.0, reference_mean=3.0, reference_std=2.0) == pytest.approx(1.0)


def test_zscore_at_mean_is_zero():
    assert zscore(3.0, reference_mean=3.0, reference_std=2.0) == pytest.approx(0.0)


def test_zscore_zero_std_raises():
    with pytest.raises(ValueError, match="reference_std"):
        zscore(5.0, reference_mean=3.0, reference_std=0.0)


def test_zscore_negative_std_raises():
    with pytest.raises(ValueError, match="reference_std"):
        zscore(5.0, reference_mean=3.0, reference_std=-1.0)


def test_zscore_array_population_ddof0():
    pool = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    # population mean=3, population std = sqrt(2) (ddof=0)
    result = zscore_array(np.array([5.0]), reference_pool=pool, ddof=0)
    assert result[0] == pytest.approx((5.0 - 3.0) / math.sqrt(2.0))


def test_zscore_array_sample_ddof1():
    pool = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    # sample std (ddof=1) over this pool = sqrt(2.5)
    result = zscore_array(np.array([5.0]), reference_pool=pool, ddof=1)
    assert result[0] == pytest.approx((5.0 - 3.0) / math.sqrt(2.5))


def test_ddof_choice_changes_result():
    # Demonstrates the two conventions are genuinely different -- this is
    # exactly why ddof has no default (see module docstring).
    pool = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    r0 = zscore_array(np.array([5.0]), reference_pool=pool, ddof=0)[0]
    r1 = zscore_array(np.array([5.0]), reference_pool=pool, ddof=1)[0]
    assert r0 != pytest.approx(r1)


def test_zscore_array_pool_smaller_than_ddof_raises():
    with pytest.raises(ValueError, match="ddof"):
        zscore_array(np.array([1.0]), reference_pool=np.array([5.0]), ddof=1)


def test_zscore_array_zero_variance_pool_raises():
    with pytest.raises(ValueError, match="zero variance"):
        zscore_array(np.array([1.0]), reference_pool=np.array([5.0, 5.0, 5.0]), ddof=0)


def test_zscore_array_empty_pool_raises():
    with pytest.raises(ValueError, match="non-empty"):
        zscore_array(np.array([1.0]), reference_pool=np.array([]), ddof=0)


def test_zscore_array_multiple_values():
    pool = np.array([10.0, 20.0, 30.0])  # population mean=20, std=sqrt(200/3)
    values = np.array([20.0, 10.0, 30.0])
    result = zscore_array(values, reference_pool=pool, ddof=0)
    assert result[0] == pytest.approx(0.0)
    assert result[1] < 0
    assert result[2] > 0
