"""Annotator interface: turns Observations into AnnotatedObservations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from semantic_annotator.models import AnnotatedObservation, Annotation, Observation

__version__ = "0.1.0"


@runtime_checkable
class Annotator(Protocol):
    """Anything that can turn an Observation into an AnnotatedObservation.

    Concrete annotators (rule-based, embedding-based, LLM-based, ...)
    implement this protocol. The pipeline and CLI depend only on this
    interface, never on a specific implementation.
    """

    def annotate(self, observation: Observation) -> AnnotatedObservation: ...


class PassthroughAnnotator:
    """Baseline annotator that attaches no semantic labels.

    Useful as a default/no-op implementation and as a scaffold for
    wiring the pipeline end-to-end before a real annotation model is
    plugged in.
    """

    version = __version__

    def annotate(self, observation: Observation) -> AnnotatedObservation:
        return AnnotatedObservation(
            observation=observation,
            annotations=(),
            annotated_at=datetime.now(UTC),
            annotator_version=self.version,
        )


class KeywordAnnotator:
    """Annotates observations by matching keywords found in the payload.

    A minimal, dependency-free reference implementation: it inspects the
    observation's ``payload`` for a ``"text"`` field and emits one
    annotation per configured keyword found within it.
    """

    version = __version__

    def __init__(self, keywords: dict[str, str]) -> None:
        """keywords maps a keyword to the label it should produce."""
        self._keywords = keywords

    def annotate(self, observation: Observation) -> AnnotatedObservation:
        text = str(observation.payload.get("text", "")).lower()
        annotations = tuple(
            Annotation(label=label, confidence=1.0)
            for keyword, label in self._keywords.items()
            if keyword.lower() in text
        )
        return AnnotatedObservation(
            observation=observation,
            annotations=annotations,
            annotated_at=datetime.now(UTC),
            annotator_version=self.version,
        )
