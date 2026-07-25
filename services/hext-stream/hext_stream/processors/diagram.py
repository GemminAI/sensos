"""Diagram → Rewrite reference processor."""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject


class DiagramProcessor(HEXTProcessor):
    processor_type = "diagram"
    version = "1.0.0"
    consumes = ["diagram"]
    produces = ["rewrite"]

    def process(self, event: HextObject) -> list[HextObject]:
        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="rewrite",
                parent=event,
                payload={"stage": "rewrite", "diagram_ref": event.id},
                metadata={"rewrite_step": 0},
            )
        ]
