"""
sensos.permutation — SPEC-SENSOS-RTV2-001 v1.4 Section 7.4 G2 Permutation Null Distribution
================================================================================================

Generic permutation-test mechanism, for v1.4 Section 7.4's G2 (Attribution
Identifiability): "残差寄与量 U_i = R²_full - R²_-i に対し、Permutation
帰無分布および BH 補正後 q 値と U_min (0.05) に基づき... ObservationState
の5値Enumに確定分類する."

This module implements ONLY the generic mechanism (build a null
distribution by repeated permutation; compute a p-value from it against an
observed statistic). It deliberately does NOT fix:

- how many permutations to run
- a randomization seed
- which permutation-generating procedure U_i's specific null distribution
  should use (data-dependent — the caller supplies ``permute_fn``)
- which alternative-hypothesis direction to test

v1.4 Section 7.4 gives no values or choices for any of the above — G2's
permutation count/procedure is explicitly named in the v1.4 Reality Audit
as a Specification Decision Required, not resolved here. All of these are
therefore REQUIRED parameters with no defaults; supplying a default would
silently invent a G2 protocol decision v1.4 never states.

No real Port/Attribution data exists yet (see Reality Audit) — tested
against synthetic numeric data.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np


def permutation_null_distribution(
    data: Any,
    statistic_fn: Callable[[Any], float],
    permute_fn: Callable[[Any, np.random.Generator], Any],
    *,
    n_permutations: int,
    rng_seed: int,
) -> np.ndarray:
    """
    Generic permutation null distribution: repeatedly permute ``data`` via
    ``permute_fn`` and evaluate ``statistic_fn`` on each permutation.

    ``n_permutations`` and ``rng_seed`` are REQUIRED — see module
    docstring: v1.4 Section 7.4 does not specify either for G2.
    """
    if n_permutations <= 0:
        raise ValueError(f"n_permutations must be positive, got {n_permutations}")

    rng = np.random.default_rng(rng_seed)
    results = np.empty(n_permutations, dtype=np.float64)
    for i in range(n_permutations):
        permuted = permute_fn(data, rng)
        results[i] = statistic_fn(permuted)
    return results


def permutation_pvalue(
    observed_statistic: float,
    null_distribution: np.ndarray,
    *,
    alternative: str,
) -> float:
    """
    p-value of ``observed_statistic`` against ``null_distribution``, using
    the standard "add-one" correction (Davison & Hinkley 1997) that avoids
    reporting an exact-zero p-value from a finite number of permutations:

        p = (count of null values at least as extreme as observed + 1)
            / (n_permutations + 1)

    ``alternative`` must be one of "greater", "less", "two-sided" and is
    REQUIRED — v1.4 does not state which directional test G2's U_i
    statistic should use (see module docstring); this is a protocol
    decision left to the caller.
    """
    if alternative not in ("greater", "less", "two-sided"):
        raise ValueError(f'alternative must be "greater", "less", or "two-sided", got {alternative!r}')

    null = np.asarray(null_distribution, dtype=np.float64)
    if null.ndim != 1 or null.size == 0:
        raise ValueError(f"null_distribution must be a non-empty 1D array, got shape {null.shape}")

    if alternative == "greater":
        count = int(np.sum(null >= observed_statistic))
    elif alternative == "less":
        count = int(np.sum(null <= observed_statistic))
    else:
        count = int(np.sum(np.abs(null) >= abs(observed_statistic)))

    return (count + 1) / (null.size + 1)
