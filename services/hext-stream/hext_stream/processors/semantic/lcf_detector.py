"""Diagram(stage=expansion_summary) → forwarded Diagram with metrics.LCF set.

Literal Constraint Fidelity — pure deterministic substring matching against
L_given (extracted by `instruction_processor`). No AI interpretation.

RFC-HEXT016 §5.4/§6: the empty-constraints default is now theory-overridable
via an injected `TheoryContext` — the substring-matching logic itself is
unchanged.
"""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject
from hext_stream.theory.context import TheoryContext

EMPTY_CONSTRAINTS_DEFAULT = 1.0


def compute_lcf(
    literals_given: list[str], generated_text: str, *, empty_constraints_default: float = EMPTY_CONSTRAINTS_DEFAULT
) -> float:
    if not literals_given:
        return empty_constraints_default
    preserved = sum(1 for lit in literals_given if lit in generated_text)
    return preserved / len(literals_given)


class LCFDetector(HEXTProcessor):
    processor_type = "semantic.lcf_detector"
    version = "1.0.0"
    consumes = ["diagram"]
    produces = ["diagram"]

    def __init__(self, theory_context: TheoryContext | None = None) -> None:
        super().__init__()
        self._theory_context = theory_context or TheoryContext.default()

    def process(self, event: HextObject) -> list[HextObject]:
        if event.metadata.get("stage") != "expansion_summary":
            return []

        lcf = compute_lcf(
            event.payload.get("literals_given", []),
            event.payload.get("generated_text", ""),
            empty_constraints_default=self._theory_context.coefficient(
                "lcf", "empty_constraints_default", EMPTY_CONSTRAINTS_DEFAULT
            ),
        )

        payload = dict(event.payload)
        payload["metrics"] = dict(payload.get("metrics", {}))
        payload["metrics"]["LCF"] = lcf

        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="diagram",
                parent=event,
                payload=payload,
                metadata={"stage": "expansion_summary"},
            )
        ]
