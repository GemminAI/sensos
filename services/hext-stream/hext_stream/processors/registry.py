"""Processor registry and type-based dispatch."""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor
from hext_stream.schema.base import HextObject


class ProcessorRegistry:
    """Register processors and dispatch by consumed event type."""

    def __init__(self) -> None:
        self._processors: dict[str, HEXTProcessor] = {}
        self._by_consume: dict[str, list[str]] = {}

    def register(self, processor: HEXTProcessor) -> str:
        self._processors[processor.processor_id] = processor
        for event_type in processor.consumes:
            self._by_consume.setdefault(event_type, []).append(processor.processor_id)
        return processor.processor_id

    def unregister(self, processor_id: str) -> bool:
        processor = self._processors.pop(processor_id, None)
        if processor is None:
            return False
        for event_type in processor.consumes:
            ids = self._by_consume.get(event_type, [])
            if processor_id in ids:
                ids.remove(processor_id)
            if not ids:
                self._by_consume.pop(event_type, None)
        return True

    def get(self, processor_id: str) -> HEXTProcessor | None:
        return self._processors.get(processor_id)

    def list(self) -> list[HEXTProcessor]:
        return list(self._processors.values())

    def dispatch(self, event: HextObject) -> list[HextObject]:
        """Run all processors that consume ``event.type``."""
        results: list[HextObject] = []
        for processor_id in self._by_consume.get(event.type, []):
            processor = self._processors[processor_id]
            outputs, _ = processor.process_timed(event)
            results.extend(outputs)
        return results
