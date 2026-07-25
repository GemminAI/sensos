"""RFC-NVS76 Semantic Stream implementation."""

from __future__ import annotations

from typing import List

from sensos.abi.nvs74.object import ObservationObject


class SemanticStream:
    """
    RFC-NVS76 (Stream ABI) Specification.

    Defines temporal sequence of Observation Objects generated in the Semantic Space.
    """

    def __init__(self, stream_id: str):
        self.stream_id = stream_id
        self.sequence: List[ObservationObject] = []

    def append(self, obj: ObservationObject) -> None:
        self.sequence.append(obj)

    def get_window(self, size: int = 5) -> List[ObservationObject]:
        return self.sequence[-size:]

    def __len__(self) -> int:
        return len(self.sequence)
