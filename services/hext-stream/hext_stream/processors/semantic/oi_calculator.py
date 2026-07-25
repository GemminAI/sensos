"""Diagram(stage=expansion_summary) → forwarded Diagram with metrics.OI set.

Overengineering Index (EXP-4010 §3.3): ratio of total pairwise dim-Hom over
Obj(A) to total pairwise dim-Hom over Obj(R), using the same disclosed
`count_simple_paths` dim-Hom convention as `sed_calculator`.

RFC-HEXT016 §5.4/§6: the zero-denominator guard value is now
theory-overridable via an injected `TheoryContext` — the pairwise-dimension
formula itself is unchanged.
"""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject
from hext_stream.schema.semantic import count_simple_paths
from hext_stream.theory.context import TheoryContext

ZERO_DENOMINATOR_DEFAULT = 1.0


def _total_pairwise_dim(graph: dict) -> float:
    objects = graph.get("objects", [])
    total = 0.0
    for a in objects:
        for b in objects:
            total += count_simple_paths(graph, a, b)
    return total


def compute_oi(
    generated_graph: dict, required_graph: dict, *, zero_denominator_default: float = ZERO_DENOMINATOR_DEFAULT
) -> float:
    numerator = _total_pairwise_dim(generated_graph)
    denominator = _total_pairwise_dim(required_graph)
    if denominator <= 0:
        denominator = zero_denominator_default
    return numerator / denominator


class OICalculator(HEXTProcessor):
    processor_type = "semantic.oi_calculator"
    version = "1.0.0"
    consumes = ["diagram"]
    produces = ["diagram"]

    def __init__(self, theory_context: TheoryContext | None = None) -> None:
        super().__init__()
        self._theory_context = theory_context or TheoryContext.default()

    def process(self, event: HextObject) -> list[HextObject]:
        if event.metadata.get("stage") != "expansion_summary":
            return []

        oi = compute_oi(
            event.payload.get("generated_graph", {}),
            event.payload.get("required_graph", {}),
            zero_denominator_default=self._theory_context.coefficient(
                "oi", "zero_denominator_default", ZERO_DENOMINATOR_DEFAULT
            ),
        )

        payload = dict(event.payload)
        payload["metrics"] = dict(payload.get("metrics", {}))
        payload["metrics"]["OI"] = oi

        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="diagram",
                parent=event,
                payload=payload,
                metadata={"stage": "expansion_summary"},
            )
        ]
