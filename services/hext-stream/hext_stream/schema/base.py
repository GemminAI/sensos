"""HEXT Object envelope — canonical ABI for all stream payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HextObjectType(str, Enum):
    OBSERVATION = "observation"
    TRAJECTORY = "trajectory"
    TRAJECTORY_FLOW = "trajectory.flow"
    REPLAY = "replay"
    CONTROLLER = "controller"
    REALITY = "reality"
    DIAGNOSTIC = "diagnostic"
    METRICS = "metrics"
    # v1.1 Processor Extension — ordinary HextObject types, no transport changes
    HOM = "hom"
    DIAGRAM = "diagram"
    REWRITE = "rewrite"
    KAN_COMPLETION = "kan_completion"
    CONTROLLER_COMMAND = "controller.command"
    SURFACE = "surface"
    # EXP-4010 Semantic Observation Processor Extension
    EXPANSION_CANDIDATE = "expansion.candidate"
    SEMANTIC_METRIC = "semantic.metric"
    # RC1 Theory Runtime / DevTools Human Annotation — domain objects, not
    # telemetry-about-the-runtime (RFC-HEXT014 §1's RC1 clarification)
    THEORY_CONFIG = "theory.config"
    HUMAN_FEEDBACK = "human.feedback"


class HextObject(BaseModel):
    """
    Canonical HEXT STREAM envelope.

    Every published event is a typed HextObject — never a raw JSON blob.
    Payloads may contain tensors, trajectory references, topology signatures,
    semantic graphs, or future HEXT structures.
    """

    id: str = Field(default_factory=lambda: f"hext:{uuid4()}")
    timestamp: datetime = Field(default_factory=utcnow)
    source: str = Field(..., description="Publishing component identifier")
    type: str = Field(..., description="HEXT object type discriminator")
    version: str = Field(default="1.0.0")
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _ensure_utc(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value

    def to_envelope(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_envelope(cls, data: dict[str, Any]) -> HextObject:
        return cls.model_validate(data)
