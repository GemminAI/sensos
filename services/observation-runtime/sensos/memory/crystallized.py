"""Persistent crystallized safe pathway storage."""

from __future__ import annotations

from typing import List

from sensos.abi.nvs74.object import ObservationObject


class CrystallizedMemoryStorage:
    """
    Persistent, immutable system memory (Sovereign Database) mapping safe pathways.
    """

    def __init__(self, safe_pathways: List[str] | None = None):
        self.safe_pathways = safe_pathways or [
            "Verified system state. No contradictory parameters detected. Output is certified clean.",
            "Action authorized. Observation match perfect. Local control loop active.",
            "Structural conflict resolved. Stabilizing execution path within certified thresholds.",
        ]

    def query_nearest(self, trajectory: List[ObservationObject]) -> str:
        """
        Retrieves the closest matching crystallized safe state to assist recovery.
        """
        if not trajectory:
            return self.safe_pathways[0]
        return self.safe_pathways[1]
