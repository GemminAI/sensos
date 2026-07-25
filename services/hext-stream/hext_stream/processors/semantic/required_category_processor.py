"""Diagram(stage=instruction) → Diagram(stage=required_category).

Normalizes the fixed, human-authored R graph fixture (already embedded in the
seed payload — never inferred here) into canonical {objects, morphisms} shape.
"""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject


def _normalize_graph(graph: dict) -> dict:
    objects = sorted(set(graph.get("objects", [])))
    morphisms = [[a, b] for a, b in graph.get("morphisms", [])]
    return {"objects": objects, "morphisms": morphisms}


class RequiredCategoryProcessor(HEXTProcessor):
    processor_type = "semantic.required_category"
    version = "1.0.0"
    consumes = ["diagram"]
    produces = ["diagram"]

    def process(self, event: HextObject) -> list[HextObject]:
        if event.metadata.get("stage") != "instruction":
            return []

        payload = dict(event.payload)
        payload["stage"] = "required_category"
        payload["required_graph"] = _normalize_graph(payload.get("required_graph", {}))

        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="diagram",
                parent=event,
                payload=payload,
                metadata={"stage": "required_category"},
            )
        ]
