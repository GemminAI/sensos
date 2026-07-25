"""Base processor types and metadata helpers for HEXT STREAM v1.1."""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from hext_stream.schema.base import HextObject, utcnow


PROCESSOR_METADATA_KEY = "processor"


class HEXTProcessor(ABC):
    """Stateless reference processor — semantic logic lives outside HEXT STREAM."""

    processor_type: str
    version: str
    consumes: list[str]
    produces: list[str]

    def __init__(self) -> None:
        self.processor_id = f"proc-{uuid.uuid4().hex[:12]}"

    @abstractmethod
    def process(self, event: HextObject) -> list[HextObject]:
        """Transform one event into zero or more derived events."""

    def process_timed(self, event: HextObject) -> tuple[list[HextObject], float]:
        start = time.perf_counter()
        outputs = self.process(event)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        stamped = [
            stamp_processor_metadata(
                out,
                self,
                execution_time_ms=elapsed_ms,
            )
            for out in outputs
        ]
        return stamped, elapsed_ms


def stamp_processor_metadata(
    obj: HextObject,
    processor: HEXTProcessor,
    *,
    execution_time_ms: float | None = None,
    parent_processor: str | None = None,
) -> HextObject:
    """Attach optional processor metadata block (backward compatible)."""
    meta = dict(obj.metadata)
    block: dict[str, Any] = {
        "id": processor.processor_id,
        "type": processor.processor_type,
        "version": processor.version,
        "input_types": list(processor.consumes),
        "output_types": list(processor.produces),
    }
    if execution_time_ms is not None:
        block["execution_time_ms"] = execution_time_ms
    if parent_processor is not None:
        block["parent_processor"] = parent_processor
    meta[PROCESSOR_METADATA_KEY] = block
    return obj.model_copy(update={"metadata": meta})


def derive_event(
    *,
    source: str,
    event_type: str,
    parent: HextObject,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> HextObject:
    """Create a derived HextObject linked to its parent."""
    meta = {"parent_id": parent.id, "derived_from": parent.id}
    if metadata:
        meta.update(metadata)
    return HextObject(
        timestamp=utcnow(),
        source=source,
        type=event_type,
        version=parent.version,
        payload=payload or {"parent_id": parent.id},
        metadata=meta,
    )
