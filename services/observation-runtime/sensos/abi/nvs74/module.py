"""RFC-NVS74 Observation Module protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class ObservationModule(ABC):
    """
    Base abstraction layer for kernel observation modules (drivers/sensors).

    Each module implements a single metric extraction function over textual
    reality streams.
    """

    @abstractmethod
    def measure(self, text: str, context: Dict[str, Any]) -> float:
        """Measure a scalar metric from the given text and observation context."""
        raise NotImplementedError
