"""
RFC-NVS74 — Observation Object ABI.

Defines the canonical representation of a single static semantic state O(t)
compiled from reality observation.
"""

from sensos.abi.nvs74.object import ObservationObject
from sensos.abi.nvs74.module import ObservationModule

__all__ = ["ObservationObject", "ObservationModule"]
