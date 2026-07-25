"""EXP-4010 payload schemas — Semantic Observation Processor Extension.

These are pure `HextObject.payload` shapes (type `expansion.candidate` /
`semantic.metric`). No existing HextObject field or ABI changes.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ExpansionCandidateType(str, Enum):
    BENEFICIAL = "beneficial"
    NEUTRAL = "neutral"
    OVERENGINEERING = "overengineering"
    CONSTRAINT_VIOLATION = "constraint_violation"


class ExpansionCandidatePayload(BaseModel):
    """Payload for a `type=expansion.candidate` HextObject.

    `trajectory_id` is required (not optional) so any candidate can be traced
    back to its full trajectory via `runtime.replay()`.
    """

    id: str
    instruction_id: str
    trajectory_id: str
    candidate_type: ExpansionCandidateType
    generated_node: str
    required_node: str | None = None
    processor: str
    metadata: dict = Field(default_factory=dict)


class MetricVectorPayload(BaseModel):
    """Payload for the single `type=semantic.metric` HextObject per trajectory.

    One Metric Object carries the whole vector — calculators merge their
    value into `metrics` instead of each publishing their own object.
    """

    instruction_id: str
    trajectory_id: str
    group: str | None = None
    # RFC-HEXT016 §10: additive; None/absent for every baseline (non-theory
    # -swapped) producer, unchanged from prior behavior. Set only by the
    # Theory Executor (RFC-HEXT016 §6) when re-running the chain under an
    # alternate TheoryConfig.
    theory_id: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)


class ControllerAction(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    SOFT_LIMIT = "soft_limit"
    HARD_LOCK = "hard_lock"


def graph_object_names(graph: dict) -> set[str]:
    """Obj(category) for a fixture graph shaped {"objects": [...], "morphisms": [[a,b], ...]}."""
    return set(graph.get("objects", []))


def count_simple_paths(graph: dict, source: str, target: str, *, max_depth: int = 6) -> int:
    """dim Hom(source, target) approximated as the count of distinct simple directed
    paths in a finite fixture graph — a concrete, disclosed realization of Hom-set
    dimension for these small graphs, not literal categorical Hom-set computation
    (same disclosed-placeholder convention as `KanProcessor`)."""
    adjacency: dict[str, list[str]] = {}
    for edge in graph.get("morphisms", []):
        a, b = edge[0], edge[1]
        adjacency.setdefault(a, []).append(b)

    if source == target:
        return 1

    count = 0

    def _walk(node: str, visited: set[str], depth: int) -> None:
        nonlocal count
        if depth > max_depth:
            return
        for nxt in adjacency.get(node, []):
            if nxt == target:
                count += 1
                continue
            if nxt not in visited:
                _walk(nxt, visited | {nxt}, depth + 1)

    _walk(source, {source}, 0)
    return count


def path_exists(graph: dict, source: str, target: str) -> bool:
    """Boolean directed reachability (BFS) — the dim-Hom realization EXP-4010 v1.0
    Candidate §3.2's Feed-Forward Detour SED formula and CTS-21 v1.0 Candidate §4.3's
    reference evaluator both use (`C_A(a,b)` as existence, not a path count). Kept
    separate from `count_simple_paths` (still used by `oi_calculator.py`, whose formula
    was not changed by the v1.0 migration)."""
    if source == target:
        return True

    adjacency: dict[str, list[str]] = {}
    for edge in graph.get("morphisms", []):
        a, b = edge[0], edge[1]
        adjacency.setdefault(a, []).append(b)

    visited: set[str] = set()
    queue: list[str] = [source]
    while queue:
        curr = queue.pop(0)
        if curr == target:
            return True
        for nxt in adjacency.get(curr, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append(nxt)
    return False
