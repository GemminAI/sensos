"""Topic routing and validation."""

from __future__ import annotations

from hext_stream.schema.base import HextObject


DEFAULT_TOPICS = (
    "Observation",
    "Trajectory",
    "TrajectoryFlow",
    "Replay",
    "Controller",
    "Reality",
    "Diagnostic",
    "Metrics",
)


class TopicRouter:
    """Validates and normalizes topic names."""

    def __init__(self, allowed_topics: list[str] | None = None) -> None:
        self._topics = set(allowed_topics or list(DEFAULT_TOPICS))

    @property
    def topics(self) -> list[str]:
        return sorted(self._topics)

    def register(self, topic: str) -> None:
        self._topics.add(topic)

    def validate(self, topic: str) -> str:
        if topic not in self._topics:
            raise ValueError(f"Unknown topic '{topic}'. Allowed: {sorted(self._topics)}")
        return topic

    def route(self, topic: str, obj: HextObject) -> tuple[str, HextObject]:
        self.validate(topic)
        return topic, obj
