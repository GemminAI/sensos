"""TrajectoryFlow → Hom + Diagram reference processor."""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject


class FlowProcessor(HEXTProcessor):
    processor_type = "flow"
    version = "1.0.0"
    consumes = ["trajectory.flow"]
    produces = ["hom", "diagram"]

    def process(self, event: HextObject) -> list[HextObject]:
        hom = derive_event(
            source=f"processor:{self.processor_type}",
            event_type="hom",
            parent=event,
            payload={"stage": "hom", "flow_ref": event.id},
            metadata={"hom_id": f"hom:{event.id}", "source_object": event.id},
        )
        diagram = derive_event(
            source=f"processor:{self.processor_type}",
            event_type="diagram",
            parent=event,
            payload={"stage": "diagram", "flow_ref": event.id},
            metadata={"diagram_id": f"diagram:{event.id}"},
        )
        return [hom, diagram]
