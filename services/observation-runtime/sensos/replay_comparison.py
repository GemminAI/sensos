"""
sensos.replay_comparison — SPEC-SENSOS-RTV2-001 v1.4 Section 7.4 G0-A / G0-B
=================================================================================

Pure comparison functions for the two TCK-v2 G0 replay gates:

- G0-A (Deterministic Replay, Strict): under identical attestation (model
  revision, runtime version, device class, precision, quantization,
  seed_set_id, sampling parameters), EOU replay MUST be bit-exact.
- G0-B (Cross-Attestation Reproducibility, Relaxed): across different
  hardware architectures, ||v - v'||_infinity <= CROSS_HARDWARE_EPSILON.

This module implements ONLY the comparison mechanics — it does not (and
cannot yet) run an actual replay, since no EOU/GPT-OSS trajectory
infrastructure exists (see Reality Audit). Tested against synthetic
numeric arrays.
"""

from __future__ import annotations

import numpy as np

from sensos.parameter_registry import DEFAULT as PARAMETER_REGISTRY


def bit_exact_match(a: np.ndarray, b: np.ndarray) -> bool:
    """
    True iff ``a`` and ``b`` have identical shape, dtype, and byte-for-byte
    representation — v1.4 Section 7.4 G0-A's "bit-exact match".

    Uses raw byte comparison rather than ``==``/``np.array_equal`` so that
    -0.0 vs 0.0 (numerically equal under ``==``, bit-different) is
    correctly treated as non-bit-exact, while identical NaN bit patterns
    (unorderable under ``==``, so `nan == nan` is False) are correctly
    treated as bit-exact when they really are byte-identical.
    """
    arr_a = np.asarray(a)
    arr_b = np.asarray(b)
    if arr_a.shape != arr_b.shape or arr_a.dtype != arr_b.dtype:
        return False
    return arr_a.tobytes() == arr_b.tobytes()


def max_norm_distance(a: np.ndarray, b: np.ndarray) -> float:
    """||a - b||_infinity, the metric v1.4 Section 7.4 G0-B is defined against."""
    arr_a = np.asarray(a, dtype=np.float64)
    arr_b = np.asarray(b, dtype=np.float64)
    if arr_a.shape != arr_b.shape:
        raise ValueError(f"shape mismatch: {arr_a.shape} vs {arr_b.shape}")
    return float(np.max(np.abs(arr_a - arr_b)))


def cross_attestation_match(
    a: np.ndarray,
    b: np.ndarray,
    *,
    epsilon: float = PARAMETER_REGISTRY.CROSS_HARDWARE_EPSILON,
) -> bool:
    """
    v1.4 Section 7.4 G0-B: ||a - b||_infinity <= epsilon. Defaults to
    v1.4's CROSS_HARDWARE_EPSILON = 1e-4 (Section 7.1 Parameter Registry)
    — legitimate as a default because, unlike the bootstrap/permutation
    protocol specifics, v1.4 explicitly supplies this exact value.
    """
    return max_norm_distance(a, b) <= epsilon
