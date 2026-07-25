"""Observation → Trajectory reference processor."""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject


class ObservationProcessor(HEXTProcessor):
    processor_type = "observation"
    version = "1.0.0"
    consumes = ["observation"]
    produces = ["trajectory"]

    def process(self, event: HextObject) -> list[HextObject]:
        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="trajectory",
                parent=event,
                payload={"stage": "trajectory", "observation_ref": event.id},
            )
        ]
