"""
sensos.triad — SPEC-SENSOS-RTV2-001 v1.4 Section 2.1 Canonical State Triad
============================================================================

Pure mathematical functions for the two numeric components of the v1.4
Section 2.1 Canonical State Record triad ``(state_hash, H_comp, Var[S])``.
``state_hash`` is handled separately (see ``sensos.canonical_hash``); this
module implements only ``Var[S]`` and ``H_comp``, as pure functions over
covariance matrices / eigenvalue arrays — not tied to any real observation,
trajectory, or hidden state (none of which exist in this repo yet; see the
Reality Audit). These functions are testable and correct today using
synthetic numeric inputs; that is a test of arithmetic correctness, not a
claim that any real Canonical Observation has been produced.

v1.4 Section 2.1 gives:
    Var[S(t)] = tr(Sigma(t))     -- trace of the ensemble covariance matrix
    H_comp(t) = -sum(lambda~_i * ln(lambda~_i))
                                  -- entropy over NORMALIZED eigenvalues

and separately asserts the *result* is bounded: "H-hat is in [0,1]".

IMPORTANT — two different things are both called "normalized" here, and
must not be conflated:

1. Normalizing the eigenvalues themselves (lambda~_i = lambda_i /
   sum(lambda_j)) so they form a probability-like distribution that sums to
   1 — this is a mathematical prerequisite for Shannon entropy to be
   defined at all, not a judgment call, and IS implemented here
   (``normalized_eigenvalues``).
2. Normalizing the *entropy value itself* into [0,1] — raw Shannon entropy
   over a d-eigenvalue distribution is bounded by [0, ln(d)], not [0,1].
   Reaching the spec's stated [0,1] bound requires an additional step
   (e.g. dividing by ln(d)) that v1.4 Section 2.1 never states. This is
   NOT implemented; ``normalized_spectral_entropy`` below raises
   ``SpecificationDecisionRequired`` rather than guessing the missing step.
"""

from __future__ import annotations

import numpy as np


class SpecificationDecisionRequired(NotImplementedError):
    """
    Raised where SPEC-SENSOS-RTV2-001 v1.4 does not specify enough to
    implement a step without guessing. Not a bug — a deliberate stop.
    """


def canonical_variance(covariance: np.ndarray, *, atol: float = 1e-8) -> float:
    """
    Var[S(t)] = tr(Sigma(t)), the trace of the ensemble covariance matrix
    (v1.4 Section 2.1).

    Validates that ``covariance`` is a real, square, symmetric,
    positive-semi-definite matrix — the mathematical precondition for
    something to legitimately be called a covariance matrix. Raises
    ValueError rather than silently computing a trace of something that
    isn't actually a valid covariance matrix.
    """
    cov = np.asarray(covariance, dtype=np.float64)

    if cov.ndim != 2 or cov.shape[0] != cov.shape[1]:
        raise ValueError(f"covariance must be a square 2D matrix, got shape {cov.shape}")
    if cov.shape[0] == 0:
        raise ValueError("covariance must not be empty (dimension mismatch)")
    if not np.allclose(cov, cov.T, atol=atol):
        raise ValueError("covariance must be symmetric")

    eigenvalues = np.linalg.eigvalsh(cov)
    if np.any(eigenvalues < -atol):
        raise ValueError(
            "covariance must be positive-semi-definite; found negative "
            f"eigenvalue(s): {eigenvalues[eigenvalues < -atol].tolist()}"
        )

    return float(np.trace(cov))


def normalized_eigenvalues(eigenvalues: np.ndarray, *, atol: float = 1e-12) -> np.ndarray:
    """
    lambda~_i = lambda_i / sum(lambda_j) — the mathematical prerequisite
    for treating eigenvalues as entropy weights (v1.4 Section 2.1 calls its
    entropy input "normalized eigenvalues lambda~_i"). This is a standard,
    unambiguous normalization, distinct from the entropy-value [0,1]
    normalization that v1.4 leaves unspecified (see module docstring).

    Raises ValueError on negative eigenvalues (not a valid covariance
    spectrum) or on an all-zero/near-zero sum (a degenerate, zero-variance
    spectrum has no defined probability-like distribution to normalize —
    this is not silently treated as zero entropy).
    """
    eig = np.asarray(eigenvalues, dtype=np.float64)
    if eig.ndim != 1 or eig.size == 0:
        raise ValueError(f"eigenvalues must be a non-empty 1D array, got shape {eig.shape}")
    if np.any(eig < -atol):
        raise ValueError(f"eigenvalues must be non-negative, got {eig.tolist()}")

    eig = np.clip(eig, 0.0, None)
    total = eig.sum()
    if total <= atol:
        raise ValueError(
            "sum of eigenvalues is zero (degenerate zero-variance spectrum); "
            "normalized eigenvalues, and therefore entropy, are undefined"
        )
    return eig / total


def raw_spectral_entropy(eigenvalues: np.ndarray) -> float:
    """
    H_comp(t) = -sum(lambda~_i * ln(lambda~_i)) (v1.4 Section 2.1), computed
    over ``normalized_eigenvalues(eigenvalues)``.

    This is the RAW Shannon entropy as literally given by the spec's
    formula — bounded in [0, ln(d)] where d is the number of eigenvalues,
    NOT bounded in [0,1]. Use this, not ``normalized_spectral_entropy``,
    unless/until the missing normalization step (see module docstring) is
    resolved by a spec revision.

    0 * ln(0) is treated as its analytic limit, 0 — standard convention for
    Shannon entropy over a distribution with zero-probability outcomes, not
    a spec judgment call.
    """
    lambda_tilde = normalized_eigenvalues(eigenvalues)
    nonzero = lambda_tilde[lambda_tilde > 0]
    return float(-np.sum(nonzero * np.log(nonzero)))


def normalized_spectral_entropy(eigenvalues: np.ndarray) -> float:
    """
    v1.4 Section 2.1 asserts the composite entropy is "H-hat in [0,1]", but
    the formula it gives (see ``raw_spectral_entropy``) only bounds the
    result in [0, ln(d)]. Reaching [0,1] requires an additional, unstated
    normalization step (e.g. dividing by ln(d), or some other convention).

    Deliberately not implemented — raises SpecificationDecisionRequired
    rather than guessing which convention v1.4 intends.
    """
    raise SpecificationDecisionRequired(
        "v1.4 Section 2.1 states H_comp's result H-hat is in [0,1] but does "
        "not specify the normalization step needed to bound raw Shannon "
        "entropy (range [0, ln(d)]) into [0,1]. Use raw_spectral_entropy() "
        "for the literal formula, or resolve this as a spec decision."
    )
