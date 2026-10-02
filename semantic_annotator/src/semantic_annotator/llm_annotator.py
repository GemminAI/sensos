"""LLM-backed Annotator: SA001's first real-inference Annotator.

Delegates all HTTP/transport concerns to a `RuntimeBridge`
(`runtime_bridge.py`) and is otherwise a plain implementation of the
existing `Annotator` protocol -- `pipeline.py` and `cli.py` need no
changes to use it, per the Annotator Protocol's own design intent
(ARCHITECTURE.md, ARCHITECTURE_REVIEW.md §2).

This module does not implement an error-handling *policy* (skip/dead-letter/
fail-fast) for the pipeline -- that is ARCHITECTURE_REVIEW.md §5's
`AnnotationError`/`on_error` proposal, deliberately out of scope for SA001
(see handoff §2, "SA001 tests exactly one thing"). It only distinguishes,
via `LLMAnnotationError`, a malformed LLM response from any other failure,
so that a caller measuring SA001's JSON Validity / Schema Conformance
metrics (handoff §7) has something typed to catch per-Observation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from semantic_annotator.models import AnnotatedObservation, Annotation, Observation
from semantic_annotator.runtime_bridge import RuntimeBridge

__version__ = "0.1.0"

_SYSTEM_PROMPT = (
    "You are a semantic annotation engine. Given a short text, respond with "
    "ONLY a JSON array of annotation objects and no other text. Each object "
    'must have exactly this shape: {"label": <string>, "confidence": '
    '<number between 0 and 1>, "taxonomy": <string or null>}. If nothing '
    "applies, respond with an empty array: []."
)


class LLMAnnotationError(Exception):
    """Base class: the LLM's raw response failed to become Annotation(s).

    Split into two subclasses because the handoff's §7 evaluation battery
    measures them as distinct metrics (JSON Validity vs. Schema
    Conformance) -- callers that need that distinction should catch the
    specific subclass rather than parse this exception's message."""


class LLMResponseNotJSONError(LLMAnnotationError):
    """The raw LLM response did not parse as JSON at all (JSON Validity)."""


class LLMSchemaViolationError(LLMAnnotationError):
    """The response parsed as JSON but didn't match the Annotation array
    shape, or a value was out of range (Schema Conformance)."""


class LLMAnnotator:
    """Annotator backed by a real LLM via a RuntimeBridge."""

    def __init__(self, bridge: RuntimeBridge, *, version: str = __version__) -> None:
        self._bridge = bridge
        self.version = version

    def annotate(self, observation: Observation) -> AnnotatedObservation:
        text = str(observation.payload.get("text", ""))
        result = self._bridge.complete(system_prompt=_SYSTEM_PROMPT, user_prompt=text)
        annotations = _parse_annotations(result.content)
        return AnnotatedObservation(
            observation=observation,
            annotations=annotations,
            annotated_at=datetime.now(UTC),
            annotator_version=self.version,
        )


def _parse_annotations(raw: str) -> tuple[Annotation, ...]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMResponseNotJSONError(f"LLM response was not valid JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise LLMSchemaViolationError(
            f"expected a JSON array of annotations, got {type(parsed).__name__}"
        )

    try:
        return tuple(
            Annotation(
                label=item["label"],
                confidence=item["confidence"],
                taxonomy=item.get("taxonomy"),
            )
            for item in parsed
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMSchemaViolationError(
            f"LLM response did not match the Annotation shape: {exc}"
        ) from exc
