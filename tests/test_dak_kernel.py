"""Tests for DAK Trajectory Differential Safety Kernel."""

from sensos.abi.nvs74.object import ObservationObject
from sensos.abi.nvs76.stream import SemanticStream
from sensos.abi.nvs76.trajectory import SemanticTrajectory
from sensos.dak.decision import DAKDecision
from sensos.dak.kernel import TrajectoryDifferentialSafetyKernel


def _append(stream: SemanticStream, kappa: float, entropy: float, similarity: float) -> None:
    stream.append(
        ObservationObject(
            step=len(stream) + 1,
            text="x",
            metrics={
                "curvature_kappa": kappa,
                "entropy_H": entropy,
                "memory_similarity": similarity,
            },
        )
    )


def test_dak_empty_trajectory_continue():
    stream = SemanticStream("s")
    dak = TrajectoryDifferentialSafetyKernel()
    risk, decision = dak.evaluate(SemanticTrajectory(stream))
    assert risk == 0.0
    assert decision == DAKDecision.CONTINUE


def test_dak_high_risk_abort():
    stream = SemanticStream("s")
    _append(stream, kappa=0.95, entropy=0.9, similarity=0.05)
    dak = TrajectoryDifferentialSafetyKernel()
    risk, decision = dak.evaluate(SemanticTrajectory(stream))
    assert risk >= 0.85
    assert decision == DAKDecision.ABORT


def test_dak_low_risk_continue():
    stream = SemanticStream("s")
    _append(stream, kappa=0.05, entropy=0.1, similarity=0.9)
    dak = TrajectoryDifferentialSafetyKernel()
    risk, decision = dak.evaluate(SemanticTrajectory(stream))
    assert decision == DAKDecision.CONTINUE
