"""Cohomological contraction validation from HEXT STREAM specification."""

from hext_stream.runtime.processors import FlowRewriteEngine
from hext_stream.schema.trajectory import EnrichedMorphism, RepresentationProfile


def test_cohomological_contraction_avoids_floor_clamping():
    engine = FlowRewriteEngine()

    current_profile = RepresentationProfile(
        curvature=210.0,
        kbd_real=2.41,
        entropy=3.10,
        adjoint_cohomology=0.45,
        tags_delta={"T18": 0.85},
    )
    target_profile = RepresentationProfile(
        curvature=15.0,
        kbd_real=1.0,
        entropy=0.8,
        adjoint_cohomology=0.01,
        tags_delta={"T18": 0.0},
    )

    lawvere_dist = engine.compute_lawvere_distance(current_profile, target_profile)
    assert lawvere_dist > 0

    current_morph = EnrichedMorphism(
        morphism_id="urn:nvs:m_id:1",
        source_0cell_id="A",
        target_0cell_id="B",
        profile=current_profile,
    )
    target_morph = EnrichedMorphism(
        morphism_id="urn:nvs:m_id:2",
        source_0cell_id="A",
        target_0cell_id="C",
        profile=target_profile,
    )
    surface = engine.generate_rewriting_2cell(current_morph, target_morph)

    assert surface.contraction_factor > 0.0
    assert surface.contraction_factor <= 0.35
