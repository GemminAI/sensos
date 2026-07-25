"""RFC-NVS76 Semantic Trajectory representation."""

from __future__ import annotations

from typing import List

from sensos.abi.nvs74.object import ObservationObject
from sensos.abi.nvs76.stream import SemanticStream


class SemanticTrajectory:
    """
    Mathematical representation of physical/logical path evolution in Semantic Space.
    """

    def __init__(self, stream: SemanticStream, window_size: int = 5):
        self.stream = stream
        self.window_size = window_size

    def get_current_trajectory(self) -> List[ObservationObject]:
        return self.stream.get_window(self.window_size)
