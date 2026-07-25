"""Observation Engine — compiles reality into RFC-NVS74 Observation Objects."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from sensos.abi.nvs74.module import ObservationModule
from sensos.abi.nvs74.object import ObservationObject
from sensos.observation.modules.curvature import CurvatureModule
from sensos.observation.modules.entropy import EntropyModule
from sensos.observation.modules.memory_similarity import MemorySimilarityModule


class ObservationEngine:
    """
    Subsystem responsible for executing diverse observation modules and compiling
    raw physical/textual reality data into structured RFC-NVS74 Observation Objects.
    """

    def __init__(self, modules: Optional[Mapping[str, ObservationModule]] = None):
        self.modules: Dict[str, ObservationModule] = dict(modules) if modules else {
            "curvature_kappa": CurvatureModule(),
            "entropy_H": EntropyModule(),
            "memory_similarity": MemorySimilarityModule(),
        }

    def register_module(self, name: str, module: ObservationModule) -> None:
        """Register or replace an observation module at runtime."""
        self.modules[name] = module

    def observe(self, step: int, text: str, context: Dict[str, Any]) -> ObservationObject:
        """
        Executes all active observation modules and crystallizes an ObservationObject.
        """
        metrics = {name: module.measure(text, context) for name, module in self.modules.items()}
        return ObservationObject(step=step, text=text, metrics=metrics)
