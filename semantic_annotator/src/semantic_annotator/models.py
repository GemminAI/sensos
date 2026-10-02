"""Domain models for Reality Observations and Annotated Observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Observation:
    """A raw observation as produced by SensOS's Reality layer.

    This is the unannotated input to the semantic-annotator: a single
    fact about the world captured by a sensor or upstream system, with
    no semantic interpretation applied yet.
    """

    id: str
    source: str
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Annotation:
    """A single semantic label attached to an observation."""

    label: str
    confidence: float
    taxonomy: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


@dataclass(frozen=True, slots=True)
class AnnotatedObservation:
    """An Observation enriched with semantic Annotations.

    This is the output contract of the semantic-annotator: everything
    downstream in SensOS consumes AnnotatedObservations, not raw
    Observations.
    """

    observation: Observation
    annotations: tuple[Annotation, ...]
    annotated_at: datetime
    annotator_version: str
