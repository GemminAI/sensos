"""
SensOS v2.0 — Observation-Centered Reality OS Kernel.

First production-quality implementation of the SensOS Kernel subsystems:
Kernel Executive, Observation Engine, DAK, and Runtime Plugin API.
"""

__version__ = "0.3.0"

from sensos.dak.decision import DAKDecision
from sensos.kernel.executive import KernelExecutive
from sensos.memory.crystallized import CrystallizedMemoryStorage
from sensos.observation.engine import ObservationEngine
from sensos.runtime.registry import RuntimePluginRegistry

__all__ = [
    "__version__",
    "DAKDecision",
    "KernelExecutive",
    "CrystallizedMemoryStorage",
    "ObservationEngine",
    "RuntimePluginRegistry",
]
