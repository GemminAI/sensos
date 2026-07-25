"""Diagram(stage=required_category) → Diagram(stage=generated_category).

Normalizes the agent's implementation trajectory (A graph + raw generated
text, both already embedded in the seed payload — this phase is Replay-only,
no live generation) into canonical {objects, morphisms} shape.
"""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject


def _normalize_graph(graph: dict) -> dict:
    objects = sorted(set(graph.get("objects", [])))
    morphisms = [[a, b] for a, b in graph.get("morphisms", [])]
    return {"objects": objects, "morphisms": morphisms}


class GeneratedCategoryProcessor(HEXTProcessor):
    processor_type = "semantic.generated_category"
    version = "1.0.0"
    consumes = ["diagram"]
    produces = ["diagram"]

    def process(self, event: HextObject) -> list[HextObject]:
        if event.metadata.get("stage") != "required_category":
            return []

        payload = dict(event.payload)
        payload["stage"] = "generated_category"
        payload["generated_graph"] = _normalize_graph(payload.get("generated_graph", {}))

        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="diagram",
                parent=event,
                payload=payload,
                metadata={"stage": "generated_category"},
            )
        ]
