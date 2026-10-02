"""semantic-annotator: the observation interface of SensOS.

Converts Reality Observations into Annotated Observations.
"""

from semantic_annotator.annotator import Annotator, KeywordAnnotator, PassthroughAnnotator
from semantic_annotator.cli import main
from semantic_annotator.models import AnnotatedObservation, Annotation, Observation
from semantic_annotator.pipeline import run_pipeline

__all__ = [
    "AnnotatedObservation",
    "Annotation",
    "Annotator",
    "KeywordAnnotator",
    "Observation",
    "PassthroughAnnotator",
    "main",
    "run_pipeline",
]
