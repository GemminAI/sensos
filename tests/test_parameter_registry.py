"""Tests for the SPEC-SENSOS-RTV2-001 v1.4 Section 7.1 Parameter Registry."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from sensos.parameter_registry import DEFAULT, SPEC_ID, SPEC_REVISION, ParameterRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = REPO_ROOT / "configs" / "parameter_registry.yaml"

# Frozen values, transcribed directly from SPEC-SENSOS-RTV2-001 v1.4 Section 7.1.
EXPECTED = {
    "AEC_THRESHOLD_V1": 0.90,
    "CROSS_HARDWARE_EPSILON": 1e-4,
    "MIN_EFFECT_SIZE_DELTA": 0.05,
    "FDR_BENJAMINI_HOCHBERG_Q": 0.05,
    "CRYSTAL_VAR_EPSILON": 0.01,
    "CRYSTAL_ENTROPY_EPSILON": 0.05,
    "PLASMA_ENTROPY_DELTA": 0.05,
    "PLASMA_VAR_MAX": 10.0,
}


def test_defaults_match_frozen_spec_values():
    for key, value in EXPECTED.items():
        assert getattr(DEFAULT, key) == value


def test_registry_has_no_undeclared_fields():
    field_names = {f.name for f in dataclasses.fields(ParameterRegistry)}
    assert field_names == set(EXPECTED.keys())


def test_registry_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT.AEC_THRESHOLD_V1 = 0.5  # type: ignore[misc]


def test_spec_identity():
    assert SPEC_ID == "SPEC-SENSOS-RTV2-001"
    assert SPEC_REVISION == "v1.4"


def test_reference_yaml_exists_and_matches_dataclass():
    assert YAML_PATH.exists(), f"expected reference YAML at {YAML_PATH}"
    loaded = ParameterRegistry.from_yaml(YAML_PATH)
    assert loaded == DEFAULT


def test_from_yaml_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        ParameterRegistry.from_yaml(tmp_path / "does_not_exist.yaml")


def test_from_yaml_rejects_value_divergence(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "parameter_registry:\n"
        "  AEC_THRESHOLD_V1: 0.5\n"  # diverges from spec on purpose
        "  CROSS_HARDWARE_EPSILON: 1e-4\n"
        "  MIN_EFFECT_SIZE_DELTA: 0.05\n"
        "  FDR_BENJAMINI_HOCHBERG_Q: 0.05\n"
        "  CRYSTAL_VAR_EPSILON: 0.01\n"
        "  CRYSTAL_ENTROPY_EPSILON: 0.05\n"
        "  PLASMA_ENTROPY_DELTA: 0.05\n"
        "  PLASMA_VAR_MAX: 10.0\n"
    )
    with pytest.raises(ValueError, match="diverge"):
        ParameterRegistry.from_yaml(bad)


def test_from_yaml_rejects_missing_keys(tmp_path):
    bad = tmp_path / "incomplete.yaml"
    bad.write_text("parameter_registry:\n  AEC_THRESHOLD_V1: 0.90\n")
    with pytest.raises(ValueError, match="missing required keys"):
        ParameterRegistry.from_yaml(bad)


def test_from_yaml_rejects_missing_block(tmp_path):
    bad = tmp_path / "no_block.yaml"
    bad.write_text("something_else: true\n")
    with pytest.raises(ValueError, match="missing top-level"):
        ParameterRegistry.from_yaml(bad)
