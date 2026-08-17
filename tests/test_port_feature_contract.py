"""
Tests for sensos.port_feature_contract (SPEC-SENSOS-RTV2-001 v1.4 Section
5.2). P17 is used below strictly as v1.4's own ONE worked example — these
tests do not assert or imply a feature mapping exists for the other 37
Ports (that remains BLOCKED_BY_SPEC_DECISION).
"""

from __future__ import annotations

import dataclasses

import pytest
from sensos.port_feature_contract import PortFeatureContract


def _p17_worked_example(**overrides):
    fields = {
        "port_id": "P17",
        "output_dim": 1,
        "readout_source": "curvature",
        "layer_range": (12, 24),
        "reduction": "L2norm",
        "standardize": True,
    }
    fields.update(overrides)
    return PortFeatureContract(**fields)


def test_v14_worked_example_constructs_successfully():
    contract = _p17_worked_example()
    assert contract.port_id == "P17"
    assert contract.output_dim == 1
    assert contract.readout_source == "curvature"
    assert contract.layer_range == (12, 24)
    assert contract.reduction == "L2norm"
    assert contract.standardize is True


def test_is_immutable():
    contract = _p17_worked_example()
    with pytest.raises(dataclasses.FrozenInstanceError):
        contract.output_dim = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# port_id format validation (P01-P38 per v1.4 Section 5.1 SSOT)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("port_id", ["P01", "P09", "P10", "P17", "P38"])
def test_valid_port_id_boundaries(port_id):
    _p17_worked_example(port_id=port_id)


@pytest.mark.parametrize(
    "port_id",
    ["P00", "P39", "P99", "P1", "p17", "P17X", "", "P017", "17", "Q17"],
)
def test_invalid_port_id_rejected(port_id):
    with pytest.raises(ValueError, match="port_id"):
        _p17_worked_example(port_id=port_id)


# ---------------------------------------------------------------------------
# output_dim validation
# ---------------------------------------------------------------------------


def test_output_dim_zero_rejected():
    with pytest.raises(ValueError, match="output_dim"):
        _p17_worked_example(output_dim=0)


def test_output_dim_negative_rejected():
    with pytest.raises(ValueError, match="output_dim"):
        _p17_worked_example(output_dim=-1)


def test_output_dim_positive_accepted():
    _p17_worked_example(output_dim=5)


# ---------------------------------------------------------------------------
# layer_range validation
# ---------------------------------------------------------------------------


def test_layer_range_descending_rejected():
    with pytest.raises(ValueError, match="layer_range"):
        _p17_worked_example(layer_range=(24, 12))


def test_layer_range_negative_rejected():
    with pytest.raises(ValueError, match="layer_range"):
        _p17_worked_example(layer_range=(-1, 5))


def test_layer_range_wrong_length_rejected():
    with pytest.raises(ValueError, match="layer_range"):
        _p17_worked_example(layer_range=(1, 2, 3))


def test_layer_range_equal_bounds_accepted():
    # a single-layer readout (lo == hi) is a valid degenerate range
    _p17_worked_example(layer_range=(12, 12))


def test_layer_range_accepts_list_input():
    # v1.4's own YAML example is a JSON/YAML list, not a tuple
    _p17_worked_example(layer_range=[12, 24])


# ---------------------------------------------------------------------------
# readout_source / reduction — free-form strings, NOT closed enums
# (v1.4 gives one example each, never an exhaustive valid set)
# ---------------------------------------------------------------------------


def test_readout_source_empty_rejected():
    with pytest.raises(ValueError, match="readout_source"):
        _p17_worked_example(readout_source="")


def test_reduction_empty_rejected():
    with pytest.raises(ValueError, match="reduction"):
        _p17_worked_example(reduction="")


@pytest.mark.parametrize("readout_source", ["curvature", "some_other_future_readout"])
def test_readout_source_is_not_a_closed_enum(readout_source):
    # Deliberately proving the field is NOT restricted to "curvature" only —
    # v1.4 never enumerates the full valid set, so no closed-set check exists.
    _p17_worked_example(readout_source=readout_source)


@pytest.mark.parametrize("reduction", ["L2norm", "some_other_future_reduction"])
def test_reduction_is_not_a_closed_enum(reduction):
    _p17_worked_example(reduction=reduction)


# ---------------------------------------------------------------------------
# standardize — MUST be True, no per-port opt-out (v1.4 Section 5.2)
# ---------------------------------------------------------------------------


def test_standardize_false_rejected():
    with pytest.raises(ValueError, match="standardize"):
        _p17_worked_example(standardize=False)


def test_standardize_true_accepted():
    _p17_worked_example(standardize=True)
