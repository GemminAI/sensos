"""
sensos.block_bootstrap — SPEC-SENSOS-RTV2-001 v1.4 Section 7.3 Seed-Level Block Bootstrap
=============================================================================================

Generic seed-cluster resampling mechanism, per v1.4 Section 7.3:

    "G1 および G2 の帰無分布構築においては、シード sigma_k（128 クラスタ）を
    再抽出単位とする Block Bootstrap を MUST 要件とする。1 ポートあたりの
    896 観測値を独立サンプルとして取り扱ってはならない。"

i.e. the resampling unit is the CLUSTER (a seed's full set of per-port
values), never an individual observation — this is what makes it a block
bootstrap rather than a naive bootstrap, and is the mechanism v1.4 mandates
to avoid a design-effect variance underestimate.

This module implements ONLY the generic mechanism. It deliberately does
NOT fix:

- bootstrap iteration count
- a randomization seed
- a confidence-interval estimator

v1.4 gives no values for any of these — they are experimental-protocol
decisions for G1/G2 specifically, not part of this generic utility.
``n_iterations`` and ``rng_seed`` are therefore REQUIRED keyword
arguments with no default; supplying a default here would silently invent
a V2.0 norm value v1.4 never states.

No real seed-cluster data exists yet (no EOU-128-v1 implementation, no
real Port observations — see Reality Audit); tested against synthetic
cluster data.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from typing import Any

import numpy as np

Resample = list[tuple[Hashable, Sequence[Any]]]


def block_bootstrap(
    data: Mapping[Hashable, Sequence[Any]],
    statistic_fn: Callable[[Resample], float],
    *,
    n_iterations: int,
    rng_seed: int,
) -> np.ndarray:
    """
    Resample by cluster (v1.4 Section 7.3: seed sigma_k as the resampling
    unit), not by individual observation.

    ``data`` maps cluster_id -> the full sequence of values belonging to
    that cluster (e.g. ``{seed_id: [port_1_value, ..., port_7_value]}`` for
    a 128-seed stateless pool). Each iteration draws ``len(data)`` cluster
    ids WITH replacement from ``data``'s keys and passes ``statistic_fn`` a
    list of ``(cluster_id, values)`` pairs — including duplicate entries
    when a cluster is drawn more than once, so each drawn cluster's full,
    intact value sequence contributes its whole block, never split across
    resamples.

    ``n_iterations`` and ``rng_seed`` are REQUIRED, not defaulted — see
    module docstring.
    """
    cluster_ids = list(data.keys())
    n_clusters = len(cluster_ids)
    if n_clusters == 0:
        raise ValueError("data must contain at least one cluster")
    if n_iterations <= 0:
        raise ValueError(f"n_iterations must be positive, got {n_iterations}")

    rng = np.random.default_rng(rng_seed)
    results = np.empty(n_iterations, dtype=np.float64)
    index_pool = np.arange(n_clusters)
    for i in range(n_iterations):
        drawn = rng.choice(index_pool, size=n_clusters, replace=True)
        resample: Resample = [(cluster_ids[idx], data[cluster_ids[idx]]) for idx in drawn]
        results[i] = statistic_fn(resample)
    return results


def flatten_resample(resample: Resample) -> list[Any]:
    """
    Flatten a block-bootstrap resample into one pooled list of individual
    values, preserving duplication when a cluster was drawn more than
    once. Pure convenience for simple ``statistic_fn`` implementations
    (e.g. a resampled mean); not itself a protocol decision.
    """
    flat: list[Any] = []
    for _cluster_id, values in resample:
        flat.extend(values)
    return flat
