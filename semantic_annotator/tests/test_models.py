from datetime import UTC, datetime

import pytest

from semantic_annotator.models import AnnotatedObservation, Annotation, Observation


def test_annotation_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError, match="confidence must be in"):
        Annotation(label="cat", confidence=1.5)


def test_annotation_accepts_boundary_confidence() -> None:
    assert Annotation(label="cat", confidence=0.0).confidence == 0.0
    assert Annotation(label="cat", confidence=1.0).confidence == 1.0


def test_annotated_observation_wraps_observation(observation: Observation) -> None:
    annotation = Annotation(label="animal", confidence=0.9)
    annotated = AnnotatedObservation(
        observation=observation,
        annotations=(annotation,),
        annotated_at=datetime(2026, 1, 1, tzinfo=UTC),
        annotator_version="0.1.0",
    )

    assert annotated.observation is observation
    assert annotated.annotations == (annotation,)
