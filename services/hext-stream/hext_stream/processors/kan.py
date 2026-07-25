"""Diagram + Hom → Kan completion placeholder (no theorem proving)."""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject


class KanProcessor(HEXTProcessor):
    processor_type = "kan"
    version = "1.0.0"
    consumes = ["diagram", "hom"]
    produces = ["kan_completion"]

    def process(self, event: HextObject) -> list[HextObject]:
        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="kan_completion",
                parent=event,
                payload={
                    "stage": "kan_completion",
                    "placeholder": True,
                    "input_ref": event.id,
                    "input_type": event.type,
                },
                metadata={"kan_status": "placeholder"},
            )
        ]
