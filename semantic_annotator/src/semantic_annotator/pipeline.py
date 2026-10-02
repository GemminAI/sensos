"""Orchestrates running an Annotator over a stream of Observations."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from semantic_annotator.annotator import Annotator
from semantic_annotator.models import AnnotatedObservation, Observation


def run_pipeline(
    observations: Iterable[Observation], annotator: Annotator
) -> Iterator[AnnotatedObservation]:
    """Annotate each Observation in order, streaming results lazily."""
    for observation in observations:
        yield annotator.annotate(observation)
