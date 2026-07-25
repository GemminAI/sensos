"""Observation topic schemas (0-cell snapshots)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from hext_stream.schema.base import HextObject, HextObjectType, utcnow


class Observation0Cell(BaseModel):
    """SFP Level 1-3 instantaneous snapshot (0-cell)."""

    id: str = Field(..., description="URN observation id (urn:nvs:observation:...)")
    timestamp: datetime = Field(default_factory=utcnow)
    sequence: int = Field(..., description="Session sequence index")
    hidden_state: list[float] | None = Field(
        None, description="Decoder final-layer vector or compressed invariant state"
    )


class ObservationEvent(BaseModel):
    """Typed Observation topic payload."""

    observation: Observation0Cell
    telemetry: dict[str, Any] = Field(default_factory=dict)
    session_id: str = ""
    model_name: str = ""

    def to_hext(self, *, source: str) -> HextObject:
        return HextObject(
            source=source,
            type=HextObjectType.OBSERVATION.value,
            version="1.0.0",
            payload=self.model_dump(mode="json"),
            metadata={"session_id": self.session_id, "model_name": self.model_name},
        )
