"""Reactive processors — morphism extraction and flow rewrite."""

from __future__ import annotations

from typing import Any

import numpy as np

from hext_stream.schema.observation import Observation0Cell
from hext_stream.schema.trajectory import (
    EnrichedMorphism,
    EnrichedSurface2Morphism,
    RepresentationProfile,
)


class TrajectoryFlowExtractor:
    """Compile 0-cell observations into 1-cell enriched morphisms."""

    def __init__(self, hidden_dim: int = 1536) -> None:
        self.hidden_dim = hidden_dim
        self.prev_observation: Observation0Cell | None = None

    def on_observation_received(
        self, current: Observation0Cell, telemetry_data: dict[str, Any]
    ) -> EnrichedMorphism:
        morphism_id = f"urn:nvs:morphism:{current.id}"
        profile = RepresentationProfile(
            curvature=float(telemetry_data["curvature"]),
            kbd_real=float(telemetry_data["kbd_real"]),
            entropy=float(telemetry_data["entropy"]),
            adjoint_cohomology=float(telemetry_data.get("acr_proxy", 1.0)),
            tags_delta=telemetry_data.get("tags_delta", {}),
        )
        morphism = EnrichedMorphism(
            morphism_id=morphism_id,
            source_0cell_id=self.prev_observation.id if self.prev_observation else "urn:nvs:observation:origin",
            target_0cell_id=current.id,
            profile=profile,
        )
        self.prev_observation = current
        return morphism


class FlowRewriteEngine:
    """Build 2-cell rewrite surfaces using Lawvere distance contraction."""

    def compute_lawvere_distance(
        self, current: RepresentationProfile, target: RepresentationProfile
    ) -> float:
        d_curv = abs(current.curvature - target.curvature)
        d_kbd = abs(current.kbd_real - target.kbd_real)
        d_acr = abs(current.adjoint_cohomology - target.adjoint_cohomology)
        return float(d_curv + d_kbd + d_acr)

    def generate_rewriting_2cell(
        self, current_morphism: EnrichedMorphism, target_morphism: EnrichedMorphism
    ) -> EnrichedSurface2Morphism:
        dist = self.compute_lawvere_distance(
            current_morphism.profile, target_morphism.profile
        )
        contraction_factor = float(np.clip(1.0 - np.exp(-0.4 * dist), 0.0, 0.35))
        semantic_diff: dict[str, float] = {}
        all_tags = set(current_morphism.profile.tags_delta) | set(
            target_morphism.profile.tags_delta
        )
        for tag in all_tags:
            semantic_diff[tag] = (
                target_morphism.profile.tags_delta.get(tag, 0.0)
                - current_morphism.profile.tags_delta.get(tag, 0.0)
            )
        return EnrichedSurface2Morphism(
            surface_id=f"urn:nvs:surface:rewrite-{current_morphism.morphism_id}",
            source_morphism_id=current_morphism.morphism_id,
            target_morphism_id=target_morphism.morphism_id,
            lawvere_distance=dist,
            contraction_factor=contraction_factor,
            semantic_shift_direction=semantic_diff,
        )
