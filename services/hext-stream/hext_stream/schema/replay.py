"""Replay topic schemas and cursor types."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from hext_stream.schema.base import HextObject, HextObjectType


class ReplayMode(str, Enum):
    FROM_ID = "from_id"
    FROM_TIMESTAMP = "from_timestamp"
    LAST_N = "last_n"


class ReplayCursor(BaseModel):
    """Deterministic replay position."""

    topic: str
    last_event_id: str | None = None
    last_timestamp: datetime | None = None


class ReplayRequest(BaseModel):
    """Replay query parameters."""

    topic: str
    mode: ReplayMode = ReplayMode.LAST_N
    from_id: str | None = None
    from_timestamp: datetime | None = None
    last_n: int = Field(default=100, ge=1, le=10_000)


class ReplayEvent(BaseModel):
    """Replay topic payload — emitted when replay session completes."""

    topic: str
    mode: ReplayMode
    event_count: int
    first_id: str | None = None
    last_id: str | None = None

    def to_hext(self, *, source: str) -> HextObject:
        return HextObject(
            source=source,
            type=HextObjectType.REPLAY.value,
            version="1.0.0",
            payload=self.model_dump(mode="json"),
            metadata={"topic": self.topic},
        )
