"""Rewrite + TrajectoryFlow → Controller command reference processor."""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject


class ControllerProcessor(HEXTProcessor):
    processor_type = "controller"
    version = "1.0.0"
    consumes = ["rewrite", "trajectory.flow"]
    produces = ["controller.command"]

    def process(self, event: HextObject) -> list[HextObject]:
        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="controller.command",
                parent=event,
                payload={"stage": "controller.command", "input_ref": event.id},
                metadata={"command": "noop"},
            )
        ]
