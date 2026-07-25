"""Curvature (κ) observation module."""

from __future__ import annotations

from typing import Any, Dict

from sensos.abi.nvs74.module import ObservationModule


class CurvatureModule(ObservationModule):
    """
    Measures local trajectory curvature κ (contradiction markers & semantic shifts).
    """

    CONTRADICTION_MARKERS = (
        "however",
        "but",
        "error",
        "failed",
        "contradiction",
        "unfortunately",
        "instead",
        "wait",
    )

    def measure(self, text: str, context: Dict[str, Any]) -> float:
        marker_count = sum(text.lower().count(marker) for marker in self.CONTRADICTION_MARKERS)
        kappa = min(marker_count * 0.18, 1.0)
        return max(kappa, 0.05)
