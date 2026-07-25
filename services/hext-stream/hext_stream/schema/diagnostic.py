"""Diagnostic topic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hext_stream.schema.base import HextObject, HextObjectType


class DiagnosticEvent(BaseModel):
    """Diagnostic topic payload — runtime health and pipeline signals."""

    component: str
    level: str = "info"
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)

    def to_hext(self, *, source: str) -> HextObject:
        return HextObject(
            source=source,
            type=HextObjectType.DIAGNOSTIC.value,
            version="1.0.0",
            payload=self.model_dump(mode="json"),
            metadata={"level": self.level, "component": self.component},
        )
