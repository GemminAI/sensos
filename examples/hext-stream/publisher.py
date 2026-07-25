#!/usr/bin/env python3
"""Example HEXT STREAM publisher."""

from hext_stream.runtime.stream_runtime import HEXTStream
from hext_stream.schema.base import HextObject
from hext_stream.schema.observation import Observation0Cell, ObservationEvent


def main() -> None:
    stream = HEXTStream()
    obs = Observation0Cell(
        id="urn:nvs:observation:demo-001",
        sequence=1,
        hidden_state=[0.1, 0.2, 0.3],
    )
    event = ObservationEvent(
        observation=obs,
        telemetry={"curvature": 0.42, "kbd_real": 1.1, "entropy": 0.8},
        session_id="sess-demo",
        model_name="demo-model",
    )
    obj = event.to_hext(source="example-publisher")
    event_id = stream.publish("Observation", obj)
    print(f"Published Observation event_id={event_id} object_id={obj.id}")


if __name__ == "__main__":
    main()
