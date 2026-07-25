#!/usr/bin/env python3
"""Example HEXT STREAM replay client."""

from hext_stream.runtime.stream_runtime import HEXTStream
from hext_stream.schema.base import HextObject
from hext_stream.schema.replay import ReplayMode, ReplayRequest


def main() -> None:
    stream = HEXTStream()

    # Seed a few events
    for i in range(5):
        stream.publish(
            "Trajectory",
            HextObject(source="replay-demo", type="trajectory", payload={"step": i}),
        )

    # Replay last 3
    events = stream.replay(
        ReplayRequest(topic="Trajectory", mode=ReplayMode.LAST_N, last_n=3)
    )
    print(f"Replayed {len(events)} events:")
    for obj in events:
        print(f"  step={obj.payload.get('step')} id={obj.id}")


if __name__ == "__main__":
    main()
