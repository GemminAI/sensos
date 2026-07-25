#!/usr/bin/env python3
"""Example HEXT STREAM subscriber."""

import time

from hext_stream.runtime.stream_runtime import HEXTStream
from hext_stream.schema.base import HextObject


def main() -> None:
    stream = HEXTStream()

    def on_event(obj: HextObject) -> None:
        print(f"[{obj.type}] id={obj.id} source={obj.source} payload_keys={list(obj.payload)}")

    handle = stream.subscribe("Observation", on_event)
    print("Subscribed to Observation — waiting 10s for events...")
    time.sleep(10)
    stream._runtime.unsubscribe(handle)
    print("Done.")


if __name__ == "__main__":
    main()
