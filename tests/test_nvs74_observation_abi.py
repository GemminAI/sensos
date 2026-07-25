"""Tests for RFC-NVS74 Observation Object ABI."""

from sensos.abi.nvs74.object import ObservationObject
from sensos.observation.modules.curvature import CurvatureModule
from sensos.observation.modules.entropy import EntropyModule
from sensos.observation.modules.memory_similarity import MemorySimilarityModule


def test_observation_object_state_hash_is_deterministic():
    obj = ObservationObject(
        step=1,
        text="sample",
        metrics={"curvature_kappa": 0.18, "entropy_H": 0.5, "memory_similarity": 0.2},
    )
    assert obj.state_hash.startswith("SENSOS_HASH_")
    assert obj.generate_state_hash() == obj.state_hash


def test_observation_object_to_dict_preview():
    obj = ObservationObject(step=2, text="A" * 100, metrics={"curvature_kappa": 0.1})
    data = obj.to_dict()
    assert data["step"] == 2
    assert data["payload_preview"].endswith("...")


def test_curvature_module_detects_contradiction_markers():
    module = CurvatureModule()
    stable = module.measure("Verified system state.", {})
    unstable = module.measure("However, but wait error failed.", {})
    assert unstable > stable


def test_entropy_module_bounds():
    module = EntropyModule()
    value = module.measure("one two three four five six seven eight", {})
    assert 0.1 <= value <= 0.95


def test_memory_similarity_module_with_safe_memories():
    module = MemorySimilarityModule()
    context = {"safe_memories": ["Verified system state certified clean"]}
    value = module.measure("Verified system state output certified clean", context)
    assert value > 0.05
