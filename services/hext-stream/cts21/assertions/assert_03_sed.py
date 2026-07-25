"""ASSERT-03: Semantic Metric (SED Category Detour Evaluator) Conformance (CTS-21.3).

CTS-21 Specification v1.0 Candidate §4.3 — "Categorical Feed-Forward Detour Sum
Evaluator":

    SED(R,A) = Σ_{Z ∈ Obj(A)\\i(Obj(R))} ( Σ_{X,Y ∈ Obj(R)} [C_A(i(X),Z) ⊗ C_A(Z,i(Y))] )

realized (per §5's reference implementation) as boolean reachability: for each excess
node Z and each pair (X,Y) of required nodes, +1 if a path X→Z exists AND a path Z→Y
exists.

MIGRATION NOTE: this supersedes the v0.2-era "excess nodes + excess edges" reference
evaluator this module previously implemented (see
Specification_Divergence_Report.md's DIVERGENCE-01, now resolved). The real runtime
(`hext_stream/processors/semantic/sed_calculator.py`) was migrated to the identical
formula, so this now checks two independent implementations of the *same* spec, not
two different specs.
"""

from __future__ import annotations

import math
from typing import Any

from hext_stream.schema.base import HextObject
from hext_stream.schema.semantic import path_exists


def calculate_sed_reference(A_nodes: set[str], A_edges: set[tuple[str, str]], R_nodes: set[str]) -> float:
    """Ported verbatim (module-level graph shape) from CTS-21 v1.0 Candidate §5
    calculate_sed_reference — path_exists here is the same BFS reachability check as
    the reference's inline path_exists()."""
    graph = {"morphisms": [list(e) for e in A_edges]}
    excess_nodes = A_nodes.difference(R_nodes)
    sed = 0.0
    for z in excess_nodes:
        for x in R_nodes:
            for y in R_nodes:
                if path_exists(graph, x, z) and path_exists(graph, z, y):
                    sed += 1.0
    return sed


def extract(published: list[HextObject], tc: dict[str, Any]) -> tuple[set[str], set[tuple[str, str]], float | None]:
    A_nodes: set[str] = set()
    A_edges: set[tuple[str, str]] = set()
    for obs in tc["injected_observations"]:
        A_nodes |= set(obs["payload_graph"]["nodes"])
        A_edges |= {tuple(e) for e in obs["payload_graph"]["edges"]}

    real_sed = None
    metric_events = [e for e in published if e.type == "semantic.metric"]
    for e in metric_events:
        if "SED" in e.payload.get("metrics", {}):
            real_sed = e.payload["metrics"]["SED"]  # last write wins, most complete vector

    return A_nodes, A_edges, real_sed


def verify(
    A_nodes: set[str],
    A_edges: set[tuple[str, str]],
    R_nodes: set[str],
    R_edges: set[tuple[str, str]],
    hom_object_sed: float | None,
    case_id: str,
) -> tuple[bool, str]:
    """Ported verbatim from CTS-21 v1.0 Candidate §5 verify_assert_03_sed_response
    (extended with a None guard since the real runtime may not have emitted a metric
    at all; R_edges accepted for signature symmetry, unused — the v1.0 reference
    evaluator only needs R_nodes)."""
    if hom_object_sed is None:
        return False, f"[FAIL] ASSERT-03: No SED metric produced by runtime for {case_id}"
    expected_sed = calculate_sed_reference(A_nodes, A_edges, R_nodes)
    if not math.isclose(hom_object_sed, expected_sed, abs_tol=1e-5):
        return False, (
            f"[FAIL] ASSERT-03: SED value mismatch in {case_id}. "
            f"Expected {expected_sed}, got {hom_object_sed}"
        )
    return True, f"[PASS] ASSERT-03: SED response verified. SED: {hom_object_sed}"
