"""
sensos.standardization — SPEC-SENSOS-RTV2-001 v1.4 Section 5.2 z-score standardization
==========================================================================================

Pure z-score utility for the Port Feature Contract's MUST-standardize
requirement (v1.4 Section 5.2: "standardize は Stateless pool に対する
z-score standardization を MUST とする").

v1.4 does not specify whether the Stateless pool's standard deviation
should use the population (ddof=0) or sample/Bessel-corrected (ddof=1)
convention — both are standard, well-established statistical choices, and
nothing in v1.4's text picks one. Rather than silently choosing, ``ddof``
is a REQUIRED keyword argument here with no default; callers (and
eventually, a spec revision) must state which convention applies.

No real Stateless-pool data exists yet (896 observations / 7 ports x 128
seeds, per v1.4 Section 5.1's stateless-baseline definition) — these
functions are tested against synthetic numeric arrays.
"""

from __future__ import annotations

import numpy as np


def zscore(value: float, *, reference_mean: float, reference_std: float) -> float:
    """
    z = (value - reference_mean) / reference_std.

    Raises ValueError if reference_std is not strictly positive — a
    zero-variance reference pool cannot standardize anything (division by
    zero would silently produce inf/nan, not a meaningful z-score).
    """
    if reference_std <= 0:
        raise ValueError(f"reference_std must be positive to standardize against; got {reference_std}")
    return (value - reference_mean) / reference_std


def zscore_array(values: np.ndarray, *, reference_pool: np.ndarray, ddof: int) -> np.ndarray:
    """
    Standardize each element of ``values`` against the mean/std of
    ``reference_pool`` (e.g. the Stateless pool, v1.4 Section 5.1).

    ``ddof`` is required, not defaulted — see module docstring: v1.4 does
    not specify population (ddof=0) vs sample (ddof=1) convention for the
    Stateless pool's standard deviation.
    """
    vals = np.asarray(values, dtype=np.float64)
    pool = np.asarray(reference_pool, dtype=np.float64)
    if pool.ndim != 1 or pool.size == 0:
        raise ValueError(f"reference_pool must be a non-empty 1D array, got shape {pool.shape}")
    if pool.size <= ddof:
        raise ValueError(f"reference_pool size ({pool.size}) must exceed ddof ({ddof})")

    mean = pool.mean()
    std = pool.std(ddof=ddof)
    if std <= 0:
        raise ValueError("reference_pool has zero variance; cannot standardize against it")
    return (vals - mean) / std
