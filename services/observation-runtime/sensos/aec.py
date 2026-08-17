"""
sensos.aec — SPEC-SENSOS-RTV2-001 v1.4 Section 5.3 Attribution Equivalence Class
====================================================================================

Pure graph utilities for AEC construction: given a correlation matrix over
standardized Port features, build the undirected graph G=(V,E) where
(i,j) in E iff |rho_ij| >= AEC_THRESHOLD_V1 (from
``sensos.parameter_registry``, the first real consumer of that constant),
then compute its connected components — the Attribution Equivalence
Classes themselves.

v1.4 Section 5.4 is explicit that AEC != Capability Equivalence Class:
these functions produce a grouping only, never a reduction/consolidation
decision. Nothing here proposes merging, reducing, or consolidating the 38
fixed Ports (v1.4 Section 5.1 SSOT); 38->8 research is explicitly out of
scope for this runtime (v1.4 Post-v2.0 Research Backlog) and this module
does not touch it.

No real Port feature data exists yet (see Reality Audit) — these functions
are tested on synthetic correlation matrices, not real observations.

Note: Pearson correlation is invariant under any per-column affine
rescaling with positive scale, so ``correlation_matrix`` does not need its
input pre-standardized — z-scoring (``sensos.standardization``) matters
for comparing feature MAGNITUDES across ports, not for this correlation
computation itself.
"""

from __future__ import annotations

import numpy as np

from sensos.parameter_registry import DEFAULT as PARAMETER_REGISTRY


def correlation_matrix(features: np.ndarray) -> np.ndarray:
    """
    Pearson correlation matrix over columns of ``features``
    (shape: [n_observations, n_ports]). Entry (i, j) of the result is
    rho_ij between port i's and port j's feature values across
    observations.
    """
    arr = np.asarray(features, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"features must be a 2D [observations, ports] array, got shape {arr.shape}")
    if arr.shape[0] < 2:
        raise ValueError("correlation requires at least 2 observations")
    if np.any(np.std(arr, axis=0) == 0):
        raise ValueError(
            "one or more ports have zero variance across observations; "
            "correlation is undefined for a constant series"
        )
    return np.corrcoef(arr, rowvar=False)


def build_aec_graph(
    correlation: np.ndarray,
    port_ids: list[str],
    *,
    threshold: float = PARAMETER_REGISTRY.AEC_THRESHOLD_V1,
) -> dict[str, set[str]]:
    """
    v1.4 Section 5.3: (i,j) in E iff |rho_ij| >= AEC_THRESHOLD_V1.
    Returns an adjacency dict {port_id: {neighbor_port_ids}}.
    """
    corr = np.asarray(correlation, dtype=np.float64)
    n = len(port_ids)
    if corr.shape != (n, n):
        raise ValueError(f"correlation must be {n}x{n} to match {n} port_ids, got {corr.shape}")

    adjacency: dict[str, set[str]] = {pid: set() for pid in port_ids}
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if abs(corr[i, j]) >= threshold:
                adjacency[port_ids[i]].add(port_ids[j])
                adjacency[port_ids[j]].add(port_ids[i])
    return adjacency


def connected_components(adjacency: dict[str, set[str]]) -> list[set[str]]:
    """
    Connected components of the AEC graph — the Attribution Equivalence
    Classes (v1.4 Section 5.3). Standard graph traversal; no spec-specific
    judgment involved.

    v1.4 Section 5.4: an AEC is NOT a Capability Equivalence Class. This
    function returns groupings only — it makes, implies, and requires no
    Port-reduction/consolidation decision.
    """
    visited: set[str] = set()
    components: list[set[str]] = []
    for node in adjacency:
        if node in visited:
            continue
        component: set[str] = set()
        stack = [node]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            stack.extend(adjacency.get(current, set()) - visited)
        components.append(component)
    return components
