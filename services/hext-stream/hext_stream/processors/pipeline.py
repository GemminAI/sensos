"""Sequential processor pipeline — uses external publish(), never replaces it."""

from __future__ import annotations

from collections.abc import Callable

from hext_stream.processors.base import HEXTProcessor, stamp_processor_metadata
from hext_stream.schema.base import HextObject

PublishFn = Callable[[str, HextObject], str]
TopicResolver = Callable[[str], str]


DEFAULT_TOPIC_MAP: dict[str, str] = {
    "observation": "Observation",
    "trajectory": "Trajectory",
    "trajectory.flow": "TrajectoryFlow",
    "hom": "Hom",
    "diagram": "Diagram",
    "rewrite": "Rewrite",
    "kan_completion": "KanCompletion",
    "controller.command": "Controller",
    "surface": "Surface",
}


class Pipeline:
    """
    Linear processor chain with multi-output fan-out.

    publish → processor → publish → processor → publish

    Uses the caller-supplied ``publish_fn`` (e.g. ``runtime.publish``).
    HEXT STREAM Core ``publish()`` is never modified.
    """

    def __init__(
        self,
        *processors: HEXTProcessor,
        publish_fn: PublishFn,
        topic_resolver: TopicResolver | None = None,
    ) -> None:
        self._processors = list(processors)
        self._publish = publish_fn
        self._topic_for = topic_resolver or (lambda t: DEFAULT_TOPIC_MAP.get(t, t))

    def execute(self, topic: str, event: HextObject) -> list[HextObject]:
        published: list[HextObject] = []
        self._publish(topic, event)
        published.append(event)

        queue: list[HextObject] = [event]
        parent_proc_id: str | None = None

        for processor in self._processors:
            progressed = False
            next_queue: list[HextObject] = []
            for ev in queue:
                if ev.type not in processor.consumes:
                    next_queue.append(ev)
                    continue
                outputs, elapsed = processor.process_timed(ev)
                for out in outputs:
                    stamped = stamp_processor_metadata(
                        out,
                        processor,
                        execution_time_ms=elapsed,
                        parent_processor=parent_proc_id,
                    )
                    out_topic = self._topic_for(stamped.type)
                    self._publish(out_topic, stamped)
                    published.append(stamped)
                    next_queue.append(stamped)
                parent_proc_id = processor.processor_id
                progressed = True
            queue = next_queue
            if not progressed and not queue:
                break
        return published
