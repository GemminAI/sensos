"""Controller topic schemas (layer plans, steering vectors)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hext_stream.schema.base import HextObject, HextObjectType


class LayerPlanPayload(BaseModel):
    """Model adapter injection command derived from 2-cell contraction."""

    surface_id: str
    contraction_factor: float = Field(..., ge=0.0, le=0.35)
    steering_vector: list[float] = Field(default_factory=list)
    target_layers: list[int] = Field(default_factory=list)
    session_id: str = ""


class ControllerEvent(BaseModel):
    """Controller topic payload."""

    plan: LayerPlanPayload
    command: str = "apply_layer_plan"

    def to_hext(self, *, source: str) -> HextObject:
        return HextObject(
            source=source,
            type=HextObjectType.CONTROLLER.value,
            version="1.0.0",
            payload=self.model_dump(mode="json"),
            metadata={"command": self.command},
        )
