"""
sensos.fdr — SPEC-SENSOS-RTV2-001 v1.4 Section 7.1/7.4 Benjamini-Hochberg FDR correction
=============================================================================================

Standard Benjamini-Hochberg (1995) false discovery rate procedure, used by
v1.4 Section 7.4's G1 (Observation Fidelity) and G2 (Attribution
Identifiability) gates. Unlike the block-bootstrap protocol specifics
(iteration count, seed), the BH procedure ITSELF is an externally, fully
defined published algorithm — not something v1.4 invents or leaves
ambiguous — so it is implemented directly here, matching the standard
formula, and cross-checked against SciPy's own independent implementation
in tests (not merely self-consistency).

The only v1.4-supplied parameter is q = FDR_BENJAMINI_HOCHBERG_Q = 0.05
(``sensos.parameter_registry``), used as this module's default
significance level.
"""

from __future__ import annotations

import numpy as np

from sensos.parameter_registry import DEFAULT as PARAMETER_REGISTRY


def benjamini_hochberg_adjusted_pvalues(p_values: np.ndarray) -> np.ndarray:
    """
    Standard BH step-up adjusted p-values (q-values), returned in the
    ORIGINAL input order.

    q_(i) = min over j>=i of (m / j) * p_(j), enforced monotonic via a
    running minimum from the largest rank down to the smallest, then
    clipped to [0, 1].
    """
    p = np.asarray(p_values, dtype=np.float64)
    if p.ndim != 1 or p.size == 0:
        raise ValueError(f"p_values must be a non-empty 1D array, got shape {p.shape}")
    if np.any((p < 0) | (p > 1)):
        raise ValueError("p_values must all lie in [0, 1]")

    m = p.size
    order = np.argsort(p)
    ranked = p[order]
    ranks = np.arange(1, m + 1)
    raw_adjusted = ranked * m / ranks

    # Enforce monotonicity: running minimum from the largest rank backward.
    adjusted_sorted = np.minimum.accumulate(raw_adjusted[::-1])[::-1]
    adjusted_sorted = np.clip(adjusted_sorted, 0.0, 1.0)

    adjusted = np.empty(m, dtype=np.float64)
    adjusted[order] = adjusted_sorted
    return adjusted


def benjamini_hochberg_reject(
    p_values: np.ndarray,
    *,
    q: float = PARAMETER_REGISTRY.FDR_BENJAMINI_HOCHBERG_Q,
) -> np.ndarray:
    """
    Boolean rejection mask (True = reject null / significant) at FDR level
    ``q``, in the original input order. Defaults to v1.4's
    FDR_BENJAMINI_HOCHBERG_Q = 0.05 (Section 7.1 Parameter Registry) — this
    default is legitimate because, unlike bootstrap iteration count/seed,
    v1.4 explicitly supplies this exact value.
    """
    if not (0 < q < 1):
        raise ValueError(f"q must be in (0, 1), got {q}")
    adjusted = benjamini_hochberg_adjusted_pvalues(p_values)
    return adjusted <= q
