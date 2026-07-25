"""Fast unit tests for the observation engine plumbing, using FakeTrigramEncoder
(NOT the real semantic model — see fake_encoder.py docstring). These test
Projection Existence (Hypothesis 0, trivially, by construction) and the
resolver/renderer/HEXT-object-creation/theta_store wiring. Real semantic
quality (Hypotheses 1-4, SD/LDR/CRA/ARA) is validated separately against
the real encoder — see run_rfc0100_verification.py.
"""

from __future__ import annotations

import numpy as np
import pytest

from hekb_mcp.client import HekbRuntimeClient
from hekb_mcp.observation_engine import (
    AttractorResolver,
    ObservationEngine,
    Projector,
    RetrievalRenderer,
    cosine_similarity,
    l2_normalize,
    reality_distance,
)
from hekb_mcp.reference_corpus import ATTRACTORS
from hekb_mcp.tests.fake_encoder import FakeTrigramEncoder
from hekb_mcp.tests.fake_hekb_runtime import FakeHekbRuntime
from hekb_mcp.theta_store import ThetaStore


def test_l2_normalize_produces_unit_vector():
    v = np.array([3.0, 4.0])
    n = l2_normalize(v)
    assert np.isclose(np.linalg.norm(n), 1.0)


def test_cosine_similarity_identical_vectors_is_one():
    v = np.array([1.0, 2.0, 3.0])
    assert np.isclose(cosine_similarity(v, v), 1.0)


def test_projector_projection_exists_for_any_string():
    # Hypothesis 0 (Projection Existence): Pi is total by construction —
    # encode()+normalize() never raise and always return a finite, unit vector.
    encoder = FakeTrigramEncoder()
    projector = Projector(encoder)
    for text in ["", "a", "モーセに十戒を与えた、契約と律法の主", "🔥" * 50, "x" * 5000]:
        projection = projector.project(text)
        assert projection.theta.shape == (encoder.dimension,)
        assert np.all(np.isfinite(projection.theta))
        assert np.isclose(np.linalg.norm(projection.theta), 1.0)


def test_reality_distance_identical_text_is_zero():
    encoder = FakeTrigramEncoder()
    assert reality_distance("hello world", "hello world", encoder) == pytest.approx(0.0, abs=1e-9)


def test_attractor_resolver_picks_exact_canonical_match():
    encoder = FakeTrigramEncoder()
    resolver = AttractorResolver(encoder)
    projector = Projector(encoder)

    for attractor_id, definition in ATTRACTORS.items():
        theta = projector.project(definition.canonical_description).theta
        result = resolver.resolve(theta)
        assert result.attractor_id == attractor_id
        assert result.chart_id == definition.chart_id
        assert result.similarity == pytest.approx(1.0, abs=1e-9)


def test_retrieval_renderer_returns_a_known_canonical_description():
    encoder = FakeTrigramEncoder()
    renderer = RetrievalRenderer(encoder)
    projector = Projector(encoder)

    theta = projector.project(ATTRACTORS["Allah"].canonical_description).theta
    rendered = renderer.render(theta)

    assert rendered in {d.canonical_description for d in ATTRACTORS.values()}


def test_observation_engine_creates_hext_object_and_stores_theta(tmp_path):
    fake_runtime = FakeHekbRuntime()
    client = HekbRuntimeClient(base_url="http://test", transport=fake_runtime.transport())
    engine = ObservationEngine(
        client=client,
        encoder=FakeTrigramEncoder(),
        theta_store=ThetaStore(path=tmp_path / "theta_store.json"),
    )

    result = engine.observe("モーセに十戒を与えた、契約と律法の主")

    assert result.object_id >= 1
    assert len(result.theta) == FakeTrigramEncoder.dimension
    assert result.resolution.attractor_id in ATTRACTORS
    stored = engine.theta_store.load(result.object_id)
    assert stored is not None
    assert stored["theta"] == result.theta
    assert stored["metadata"]["attractor_id"] == result.resolution.attractor_id
