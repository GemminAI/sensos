"""Diagram(stage=expansion_summary) → forwarded Diagram with metrics.SED set.

Semantic Expansion Distance — EXP-4010 v1.0 Candidate §3.2, "Feed-Forward Detour"
correction:

    SED(R,A) = Σ_{Z ∈ Obj(A)\\i(Obj(R))} ( Σ_{X,Y ∈ Obj(R)} [C_A(i(X),Z) ⊗ C_A(Z,i(Y))] )

MIGRATION NOTE (superseding the v0.2 formula previously implemented here): the old
formula required a *round trip* back through the same required node
(`C_A(X,Z) ⊗ C_A(Z,X)`), which is provably 0 for any pure-DAG expansion — a disclosed
but unwanted property (see EXP-4010_Report.md and
Specification_Divergence_Report.md). EXP-4010 v1.0 Candidate fixes this by summing over
*independent* required-node pairs (X,Y) and only requiring a forward detour X→Z→Y, so a
pure feed-forward insertion like `JSON→Repository→Storage` now scores non-zero
(SED=1.0 for that canonical case) instead of collapsing to 0. `C_A` is realized as
boolean reachability (`path_exists`), matching CTS-21 v1.0 Candidate §4.3's reference
evaluator exactly — not `count_simple_paths` (kept for `oi_calculator.py`, whose formula
was not changed by this migration).
"""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject
from hext_stream.schema.semantic import path_exists
from hext_stream.theory.context import TheoryContext

# RFC-HEXT016 §2 Rule 2: SED has no coefficient in RC1 — the only literal in
# `compute_sed` is the structural per-match accumulator (`+= 1.0`), not a
# tunable constant. `theory_context` is still accepted, for constructor
# uniformity across all six processors (RFC-HEXT016 §6 Rule 1), but is
# never queried below.


def compute_sed(generated_graph: dict, required_objects: list[str], candidates: list[dict]) -> float:
    total = 0.0
    for candidate in candidates:
        z = candidate["generated_node"]
        for x in required_objects:
            for y in required_objects:
                if path_exists(generated_graph, x, z) and path_exists(generated_graph, z, y):
                    total += 1.0
    return total


class SEDCalculator(HEXTProcessor):
    processor_type = "semantic.sed_calculator"
    version = "1.1.0"
    consumes = ["diagram"]
    produces = ["diagram"]

    def __init__(self, theory_context: TheoryContext | None = None) -> None:
        super().__init__()
        self._theory_context = theory_context or TheoryContext.default()

    def process(self, event: HextObject) -> list[HextObject]:
        if event.metadata.get("stage") != "expansion_summary":
            return []

        sed = compute_sed(
            event.payload.get("generated_graph", {}),
            event.payload.get("required_graph", {}).get("objects", []),
            event.payload.get("candidates", []),
        )

        payload = dict(event.payload)
        payload["metrics"] = dict(payload.get("metrics", {}))
        payload["metrics"]["SED"] = sed

        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="diagram",
                parent=event,
                payload=payload,
                metadata={"stage": "expansion_summary"},
            )
        ]
