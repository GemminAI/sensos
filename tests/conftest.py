"""Shared pytest fixtures for SensOS Kernel tests."""

from __future__ import annotations

import pytest

from sensos.memory.crystallized import CrystallizedMemoryStorage
from sensos.observation.engine import ObservationEngine
from sensos.runtime.plugins.mock_gpt import MockGPTPlugin


@pytest.fixture
def observation_engine() -> ObservationEngine:
    return ObservationEngine()


@pytest.fixture
def memory() -> CrystallizedMemoryStorage:
    return CrystallizedMemoryStorage()


@pytest.fixture
def mock_runtime() -> MockGPTPlugin:
    return MockGPTPlugin()
