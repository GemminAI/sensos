"""Tests for Observation Engine subsystem."""

from sensos.observation.engine import ObservationEngine


def test_observation_engine_compiles_metrics(observation_engine):
    obj = observation_engine.observe(
        step=1,
        text="Verified clean state",
        context={"safe_memories": ["Verified clean state"]},
    )
    assert set(obj.metrics.keys()) == {"curvature_kappa", "entropy_H", "memory_similarity"}
    assert obj.step == 1
