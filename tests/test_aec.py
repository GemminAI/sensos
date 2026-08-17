"""
Tests for sensos.aec (SPEC-SENSOS-RTV2-001 v1.4 Section 5.3). All feature
matrices below are synthetic numeric arrays used to verify graph/statistics
arithmetic — none represent real Port observations.
"""

from __future__ import annotations

import numpy as np
import pytest
from sensos.aec import build_aec_graph, connected_components, correlation_matrix
from sensos.parameter_registry import DEFAULT as PARAMETER_REGISTRY

# ---------------------------------------------------------------------------
# correlation_matrix
# ---------------------------------------------------------------------------


def test_perfectly_correlated_columns():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    features = np.column_stack([a, 2 * a])  # perfectly positively correlated
    corr = correlation_matrix(features)
    assert corr[0, 1] == pytest.approx(1.0)
    assert corr[1, 0] == pytest.approx(1.0)


def test_perfectly_anti_correlated_columns():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    features = np.column_stack([a, -a])
    corr = correlation_matrix(features)
    assert corr[0, 1] == pytest.approx(-1.0)


def test_diagonal_is_always_one():
    features = np.column_stack([[1.0, 2.0, 3.0], [5.0, 1.0, 9.0], [2.0, 2.0, 7.0]])
    corr = correlation_matrix(features)
    assert np.allclose(np.diag(corr), 1.0)


def test_zero_variance_column_raises():
    a = np.array([1.0, 2.0, 3.0])
    constant = np.array([5.0, 5.0, 5.0])
    with pytest.raises(ValueError, match="zero variance"):
        correlation_matrix(np.column_stack([a, constant]))


def test_single_observation_raises():
    with pytest.raises(ValueError, match="at least 2 observations"):
        correlation_matrix(np.array([[1.0, 2.0, 3.0]]))


def test_non_2d_input_raises():
    with pytest.raises(ValueError, match="2D"):
        correlation_matrix(np.array([1.0, 2.0, 3.0]))


# ---------------------------------------------------------------------------
# build_aec_graph
# ---------------------------------------------------------------------------


def test_default_threshold_matches_parameter_registry():
    import inspect

    default_threshold = inspect.signature(build_aec_graph).parameters["threshold"].default
    assert default_threshold == PARAMETER_REGISTRY.AEC_THRESHOLD_V1 == 0.90


def test_edge_created_at_or_above_threshold():
    port_ids = ["P01", "P02", "P03"]
    corr = np.array(
        [
            [1.0, 0.95, 0.10],
            [0.95, 1.0, 0.05],
            [0.10, 0.05, 1.0],
        ]
    )
    adjacency = build_aec_graph(corr, port_ids, threshold=0.90)
    assert adjacency["P01"] == {"P02"}
    assert adjacency["P02"] == {"P01"}
    assert adjacency["P03"] == set()


def test_negative_correlation_at_threshold_also_creates_edge():
    # |rho_ij| >= threshold per v1.4 Section 5.3 -- sign doesn't matter.
    port_ids = ["P01", "P02"]
    corr = np.array([[1.0, -0.95], [-0.95, 1.0]])
    adjacency = build_aec_graph(corr, port_ids, threshold=0.90)
    assert adjacency["P01"] == {"P02"}


def test_exactly_at_threshold_creates_edge():
    port_ids = ["P01", "P02"]
    corr = np.array([[1.0, 0.90], [0.90, 1.0]])
    adjacency = build_aec_graph(corr, port_ids, threshold=0.90)
    assert adjacency["P01"] == {"P02"}


def test_just_below_threshold_no_edge():
    port_ids = ["P01", "P02"]
    corr = np.array([[1.0, 0.8999], [0.8999, 1.0]])
    adjacency = build_aec_graph(corr, port_ids, threshold=0.90)
    assert adjacency["P01"] == set()


def test_shape_mismatch_raises():
    with pytest.raises(ValueError, match="match"):
        build_aec_graph(np.eye(2), ["P01", "P02", "P03"])


# ---------------------------------------------------------------------------
# connected_components
# ---------------------------------------------------------------------------


def test_two_components():
    adjacency = {"P01": {"P02"}, "P02": {"P01"}, "P03": set()}
    components = connected_components(adjacency)
    assert {frozenset(c) for c in components} == {frozenset({"P01", "P02"}), frozenset({"P03"})}


def test_fully_disconnected_graph_gives_singletons():
    adjacency = {"P01": set(), "P02": set(), "P03": set()}
    components = connected_components(adjacency)
    assert sorted(components, key=lambda s: sorted(s)) == [{"P01"}, {"P02"}, {"P03"}]


def test_fully_connected_graph_gives_one_component():
    adjacency = {"P01": {"P02", "P03"}, "P02": {"P01", "P03"}, "P03": {"P01", "P02"}}
    components = connected_components(adjacency)
    assert len(components) == 1
    assert components[0] == {"P01", "P02", "P03"}


def test_chain_graph_transitively_connects():
    # P01-P02-P03 chain: P01 and P03 are not directly correlated above
    # threshold, but end up in the same AEC via P02.
    adjacency = {"P01": {"P02"}, "P02": {"P01", "P03"}, "P03": {"P02"}}
    components = connected_components(adjacency)
    assert len(components) == 1
    assert components[0] == {"P01", "P02", "P03"}


def test_aec_grouping_makes_no_reduction_claim():
    # v1.4 Section 5.4: AEC != Capability Equivalence Class. The function
    # returns a partition only; there is no "should we merge these ports"
    # output anywhere in this module.
    import sensos.aec as aec_module

    assert not hasattr(aec_module, "reduce")
    assert not hasattr(aec_module, "merge_ports")
    assert not hasattr(aec_module, "capability_equivalence")


# ---------------------------------------------------------------------------
# End-to-end pipeline on synthetic data
# ---------------------------------------------------------------------------


def test_end_to_end_pipeline_on_synthetic_features():
    port_ids = ["P01", "P02", "P03", "P04"]
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    features = np.column_stack(
        [
            a,  # P01
            2 * a + 0.001,  # P02: near-perfectly correlated with P01
            np.array([5.0, 1.0, 9.0, 2.0, 7.0, 3.0]),  # P03: unrelated
            np.array([9.0, 2.0, 8.0, 1.0, 7.0, 0.0]),  # P04: unrelated
        ]
    )
    corr = correlation_matrix(features)
    adjacency = build_aec_graph(corr, port_ids)
    components = connected_components(adjacency)
    # P01/P02 should land in the same AEC; the total partition covers all 4 ports.
    assert sum(len(c) for c in components) == 4
    same_class = next(c for c in components if "P01" in c)
    assert "P02" in same_class
