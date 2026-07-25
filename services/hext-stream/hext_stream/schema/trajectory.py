"""Trajectory and TrajectoryFlow topic schemas (1-cell / 2-cell morphisms)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from hext_stream.schema.base import HextObject, HextObjectType, utcnow


class RepresentationProfile(BaseModel):
    """Symmetric monoidal category V object — geometry, information, semantics."""

    curvature: float = Field(..., description="Local trajectory curvature")
    kbd_real: float = Field(..., description="Knowledge boundary distance composite")
    entropy: float = Field(..., description="Output token entropy flow")
    adjoint_cohomology: float = Field(..., description="Adjoint cohomology proxy (ACR)")
    tags_delta: dict[str, float] = Field(
        default_factory=dict,
        description="35TAG delta profile — morphism attribute, not static object tag",
    )

    def tensor_product(self, other: RepresentationProfile) -> RepresentationProfile:
        new_tags: dict[str, float] = {}
        for key in set(self.tags_delta) | set(other.tags_delta):
            new_tags[key] = self.tags_delta.get(key, 0.0) + other.tags_delta.get(key, 0.0)
        return RepresentationProfile(
            curvature=self.curvature + other.curvature,
            kbd_real=self.kbd_real + other.kbd_real,
            entropy=self.entropy + other.entropy,
            adjoint_cohomology=self.adjoint_cohomology + other.adjoint_cohomology,
            tags_delta=new_tags,
        )


class EnrichedMorphism(BaseModel):
    """1-cell / Hom-object between observation snapshots."""

    morphism_id: str
    source_0cell_id: str
    target_0cell_id: str
    profile: RepresentationProfile


class EnrichedSurface2Morphism(BaseModel):
    """2-cell rewrite surface between enriched morphisms."""

    surface_id: str
    source_morphism_id: str
    target_morphism_id: str
    lawvere_distance: float
    contraction_factor: float = Field(..., ge=0.0, le=0.35)
    semantic_shift_direction: dict[str, float] = Field(default_factory=dict)


class TrajectoryEvent(BaseModel):
    """Trajectory topic payload."""

    morphism: EnrichedMorphism
    session_id: str = ""
    model_name: str = ""

    def to_hext(self, *, source: str) -> HextObject:
        return HextObject(
            source=source,
            type=HextObjectType.TRAJECTORY.value,
            version="1.0.0",
            payload=self.model_dump(mode="json"),
            metadata={"session_id": self.session_id, "model_name": self.model_name},
        )


class TrajectoryFlowEvent(BaseModel):
    """TrajectoryFlow topic — morphism extraction pipeline output."""

    morphism: EnrichedMorphism
    rewrite_surface: EnrichedSurface2Morphism | None = None
    session_id: str = ""
    model_name: str = ""
    extracted_at: datetime = Field(default_factory=utcnow)

    def to_hext(self, *, source: str) -> HextObject:
        return HextObject(
            source=source,
            type=HextObjectType.TRAJECTORY_FLOW.value,
            version="1.0.0",
            payload=self.model_dump(mode="json"),
            metadata={"session_id": self.session_id, "model_name": self.model_name},
        )
