from datetime import UTC, datetime

import pytest

from semantic_annotator.models import Observation


@pytest.fixture
def observation() -> Observation:
    return Observation(
        id="obs-1",
        source="test-sensor",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        payload={"text": "a cat sat on the mat"},
    )
