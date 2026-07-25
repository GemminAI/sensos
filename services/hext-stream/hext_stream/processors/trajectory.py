"""Trajectory → TrajectoryFlow reference processor."""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject


class TrajectoryProcessor(HEXTProcessor):
    processor_type = "trajectory"
    version = "1.0.0"
    consumes = ["trajectory"]
    produces = ["trajectory.flow"]

    def process(self, event: HextObject) -> list[HextObject]:
        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="trajectory.flow",
                parent=event,
                payload={"stage": "trajectory.flow", "trajectory_ref": event.id},
            )
        ]
