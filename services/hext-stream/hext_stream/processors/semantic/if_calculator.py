"""Diagram(stage=expansion_summary) → one semantic.metric (SED, OI, IF, LCF).

Instruction Fidelity (EXP-4010 §3.1): |Obj(R) ∩ Obj(A)| / |Obj(R)|.

Last calculator in the chain — publishes the single, consolidated Metric
Object for the trajectory instead of yet another standalone metric event.

RFC-HEXT016 §5.4/§6: the empty-required-set default is now theory-overridable
via an injected `TheoryContext` — the set-intersection formula itself is
unchanged.
"""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject
from hext_stream.schema.semantic import MetricVectorPayload
from hext_stream.theory.context import TheoryContext

EMPTY_REQUIRED_DEFAULT = 1.0


def compute_if(
    required_objects: list[str], generated_objects: list[str], *, empty_required_default: float = EMPTY_REQUIRED_DEFAULT
) -> float:
    if not required_objects:
        return empty_required_default
    required_set = set(required_objects)
    generated_set = set(generated_objects)
    return len(required_set & generated_set) / len(required_set)


class IFCalculator(HEXTProcessor):
    processor_type = "semantic.if_calculator"
    version = "1.0.0"
    consumes = ["diagram"]
    produces = ["semantic.metric"]

    def __init__(self, theory_context: TheoryContext | None = None) -> None:
        super().__init__()
        self._theory_context = theory_context or TheoryContext.default()

    def process(self, event: HextObject) -> list[HextObject]:
        if event.metadata.get("stage") != "expansion_summary":
            return []

        if_score = compute_if(
            event.payload.get("required_graph", {}).get("objects", []),
            event.payload.get("generated_graph", {}).get("objects", []),
            empty_required_default=self._theory_context.coefficient(
                "if", "empty_required_default", EMPTY_REQUIRED_DEFAULT
            ),
        )

        metrics = dict(event.payload.get("metrics", {}))
        metrics["IF"] = if_score

        vector = MetricVectorPayload(
            instruction_id=event.payload.get("instruction_id", event.id),
            trajectory_id=event.payload.get("trajectory_id", event.id),
            group=event.payload.get("group"),
            metrics=metrics,
        )

        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="semantic.metric",
                parent=event,
                payload=vector.model_dump(mode="json"),
                metadata={"trajectory_id": vector.trajectory_id},
            )
        ]
