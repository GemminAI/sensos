"""Trajectory Differential Safety Kernel core engine."""

from __future__ import annotations

from typing import Tuple

from sensos.abi.nvs76.trajectory import SemanticTrajectory
from sensos.dak.decision import DAKDecision


class TrajectoryDifferentialSafetyKernel:
    """
    DAK Core Engine (v2.0).

    Evaluates semantic divergence from safety manifold and yields DAKDecision.
    """

    def __init__(
        self,
        theta_correct: float = 0.40,
        theta_escalate: float = 0.65,
        theta_abort: float = 0.85,
    ):
        self.theta_correct = theta_correct
        self.theta_escalate = theta_escalate
        self.theta_abort = theta_abort

    def evaluate(self, trajectory: SemanticTrajectory) -> Tuple[float, DAKDecision]:
        """
        Calculates dynamic risk RH(t) and maps it to policy decisions.
        """
        states = trajectory.get_current_trajectory()
        if not states:
            return 0.0, DAKDecision.CONTINUE

        last_state = states[-1]
        kappa = last_state.metrics.get("curvature_kappa", 0.0)
        entropy = last_state.metrics.get("entropy_H", 0.0)
        similarity = last_state.metrics.get("memory_similarity", 0.0)

        # Calculate Trajectory Differential: Deviation from safe crystallized manifold
        delta_t = 1.0 - similarity
        if len(states) > 1:
            prev_state = states[-2]
            pk = prev_state.metrics.get("curvature_kappa", 0.0)
            delta_t += abs(kappa - pk) * 0.4

        # Dynamic Risk Formula: RH = 0.5 * ΔT + 0.3 * κ + 0.2 * H
        risk_rh = (0.5 * delta_t) + (0.3 * kappa) + (0.2 * entropy)
        risk_rh = min(max(risk_rh, 0.0), 1.0)

        if risk_rh >= self.theta_abort:
            decision = DAKDecision.ABORT
        elif risk_rh >= self.theta_escalate:
            decision = DAKDecision.ESCALATE
        elif risk_rh >= self.theta_correct:
            decision = DAKDecision.CORRECT
        else:
            decision = DAKDecision.CONTINUE

        return risk_rh, decision
