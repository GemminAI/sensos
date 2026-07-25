"""RFC-HEXT013 §2: Observation Driver — the sole entry point for raw input.

Sequence allocation (§5.2) and digest preservation (§6) are intentionally
NOT performed here: RFC-HEXT011 §3's Runtime Scheduler needs sequence
numbers for every published stream regardless of which component
originated the object (Observation Driver, Processor Pipeline output, or a
test harness constructing a HextObject directly), so both are implemented
once, centrally, in ``StreamRuntime.publish()`` — the single funnel every
publish path passes through — rather than duplicated in this
narrower-scoped Driver. This keeps one authoritative implementation per
RFC-HEXT013 §5.2/§6, consistent with this project's "do not redefine the
same symbol twice" discipline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from hext_stream.observation import converter, grounding
from hext_stream.observation.allocators import (
    TimestampAllocator,
    allocate_uuid7,
    is_valid_uuid7,
)
from hext_stream.schema.base import HextObject


class ObservationDriver:
    """RFC-HEXT013 §2: single permitted entry point for raw external input.

    Runs §3 (conversion) -> §4 (UUID) -> §5.1 (timestamp) -> §7 (grounding),
    in that order, per RFC-HEXT013 §8 Rule 2. Sequence (§5.2) and digest
    (§6) are applied afterwards by ``StreamRuntime.publish()``.
    """

    def __init__(self) -> None:
        self._timestamps = TimestampAllocator()

    def ingest(
        self,
        *,
        stream: str,
        source: str,
        type: str,
        version: str = "1.0.0",
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        id: str | None = None,
        timestamp: datetime | None = None,
    ) -> HextObject:
        payload = payload or {}
        metadata = dict(metadata or {})

        validation = converter.convert(type_=type, payload=payload)
        metadata.setdefault("observation_runtime", {})
        metadata["observation_runtime"] = {**metadata["observation_runtime"], **validation}

        # RFC-HEXT013 §4 Rule 2: accept a caller-supplied id only if it is
        # itself a valid UUIDv7; otherwise allocate one.
        object_id = id if (id and is_valid_uuid7(id)) else allocate_uuid7()

        object_timestamp = timestamp or self._timestamps.allocate(stream)

        grounding.ground(metadata=metadata)

        return HextObject(
            id=object_id,
            timestamp=object_timestamp,
            source=source,
            type=type,
            version=version,
            payload=payload,
            metadata=metadata,
        )
