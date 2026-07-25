"""Adapter for the Semantic Annotator service: HTTP -> JSON -> Runtime model.

Dependency direction is one-way: Runtime depends on Semantic Annotator via
this module; Semantic Annotator has no knowledge of Runtime (it is a
standalone container - see ~/nvs-platform-runtime/semantic-annotator/).

This module owns the entire chain from HTTP response to typed
AnnotationResult. No other Runtime code may:
  - touch a raw JSON dict parsed from a Semantic Annotator response, or
  - know which backend Semantic Annotator uses internally (Anthropic/
    OpenAI/Gemini today; a future spaCy/GiNZA/CRF/BERT/rule-based backend
    tomorrow) - that selection is entirely Semantic Annotator's own
    configuration, never passed from here.

The only three endpoints referenced anywhere in this file are the three
Semantic Annotator publishes: POST /annotate, GET /health, GET /version.
Nothing here imports semantic-annotator/backends, /common, /app, or
/schemas - those are internal to that service.

Fail Fast: _parse_annotation() uses `[...]` (not `.get(key, default)`) for
every mandatory field, so a missing/renamed key raises KeyError
immediately and is wrapped into AnnotationBackendError. There is no
zero-vector/default fallback anywhere in this module - a malformed or
unreachable response is always a raised exception, never a silently
degraded value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from runtime.core.config import get_settings
from runtime.core.exceptions import (
    AnnotationBackendError,
    AnnotationUnavailableError,
    AnnotationValidationError,
)

# Semantic Annotator response schema_version values this adapter knows how
# to parse (see semantic-annotator/app/schemas.py::ANNOTATION_SCHEMA_VERSION,
# echoed at GET /version). Bump this set only after updating
# _parse_annotation() to match the new shape - see check_version_compatibility().
COMPATIBLE_SCHEMA_VERSIONS = {"1.0"}


@dataclass(frozen=True)
class TagsResult:
    """The only part of an Annotation Runtime currently consumes downstream
    (runtime/services/crystallizer.py's hashing/classification helpers) -
    typed field-by-field, unlike the opaque pass-through blocks on
    AnnotationResult below."""

    t09_strategic_interest_vector: dict[str, float]
    t10_epistemic_confidence: float
    t19_conflict_factuality_index: float
    t03_predicate_type: str | None = None
    t07_actor_role: dict[str, str] | None = None
    t08_causality_direction: str | None = None
    t11_bias_component: dict[str, Any] | None = None
    t16_economic_transmission_path: list[str] | None = None

    def to_legacy_dict(self) -> dict[str, Any]:
        """Flat dict for crystallizer.py's compute_epistemic_diffusion_state
        / crystallize_state_hash, which accept `tags: dict[str, Any]`
        generically and don't need an Annotation-aware signature."""
        return {
            "T09_strategic_interest_vector": self.t09_strategic_interest_vector,
            "T10_epistemic_confidence": self.t10_epistemic_confidence,
            "T19_conflict_factuality_index": self.t19_conflict_factuality_index,
            "T03_predicate_type": self.t03_predicate_type,
            "T07_actor_role": self.t07_actor_role,
            "T08_causality_direction": self.t08_causality_direction,
            "T11_bias_component": self.t11_bias_component,
            "T16_economic_transmission_path": self.t16_economic_transmission_path,
        }


@dataclass(frozen=True)
class AnnotationResult:
    """Runtime's own ABI for a Semantic Annotator annotation - defined
    here, independently of semantic-annotator's internal app.schemas.
    Annotation model. Runtime code must only ever see this type, never a
    raw dict parsed from the wire.

    subject/entities/events/time/location/metadata/confidence are kept as
    opaque dicts/lists (not further typed) because nothing in Runtime
    consumes them yet - unlike `tags` (see TagsResult). A future consumer
    should add a typed submodel analogous to TagsResult rather than
    indexing into these dicts ad hoc.
    """

    version: str
    tags: TagsResult
    subject: dict[str, Any]
    entities: list[dict[str, Any]]
    events: list[dict[str, Any]]
    time: dict[str, Any]
    location: dict[str, Any]
    metadata: dict[str, Any]
    confidence: dict[str, Any]


def _parse_annotation(body: dict[str, Any]) -> AnnotationResult:
    """The only place in Runtime allowed to index into a Semantic Annotator
    JSON response. `[...]` on every mandatory field - a missing or renamed
    key raises KeyError immediately rather than silently defaulting."""
    tags_raw = body["tags"]
    tags = TagsResult(
        t09_strategic_interest_vector=tags_raw["T09_strategic_interest_vector"],
        t10_epistemic_confidence=tags_raw["T10_epistemic_confidence"],
        t19_conflict_factuality_index=tags_raw["T19_conflict_factuality_index"],
        t03_predicate_type=tags_raw.get("T03_predicate_type"),
        t07_actor_role=tags_raw.get("T07_actor_role"),
        t08_causality_direction=tags_raw.get("T08_causality_direction"),
        t11_bias_component=tags_raw.get("T11_bias_component"),
        t16_economic_transmission_path=tags_raw.get("T16_economic_transmission_path"),
    )
    return AnnotationResult(
        version=body["version"],
        tags=tags,
        subject=body["subject"],
        entities=body["entities"],
        events=body["events"],
        time=body["time"],
        location=body["location"],
        metadata=body["metadata"],
        confidence=body["confidence"],
    )


class SemanticAnnotatorClient:
    """The only Runtime code allowed to speak HTTP to Semantic Annotator."""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or get_settings().semantic_annotator_url).rstrip("/")
        self._timeout = timeout

    async def check_version_compatibility(self) -> None:
        """Call GET /version and raise if Runtime doesn't know how to parse
        this schema_version. Intended to run once at Runtime startup (see
        runtime/main.py::on_startup) so a version-incompatible Semantic
        Annotator fails Runtime startup outright, rather than letting every
        /annotate call fail or misparse silently later."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self.base_url}/version")
                resp.raise_for_status()
                body = resp.json()
        except httpx.HTTPError as exc:
            raise AnnotationUnavailableError(
                "semantic_annotator_unreachable",
                f"Could not reach Semantic Annotator at {self.base_url}/version: {exc}",
            ) from exc

        schema_version = body.get("schema_version")
        if schema_version not in COMPATIBLE_SCHEMA_VERSIONS:
            raise AnnotationBackendError(
                "semantic_annotator_schema_drift",
                f"Semantic Annotator schema_version {schema_version!r} at "
                f"{self.base_url} is not one Runtime supports "
                f"({sorted(COMPATIBLE_SCHEMA_VERSIONS)}). Refusing to start "
                f"against an incompatible contract.",
            )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def annotate(self, text: str) -> AnnotationResult:
        """POST /annotate and parse the response into AnnotationResult.

        Deliberately takes no `provider` parameter: which backend Semantic
        Annotator uses is that service's own configuration, never
        Runtime's concern (see module docstring).
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self.base_url}/annotate", json={"text": text})
        except httpx.HTTPError as exc:
            raise AnnotationUnavailableError(
                "semantic_annotator_unreachable",
                f"Could not reach Semantic Annotator at {self.base_url}/annotate: {exc}",
            ) from exc

        if resp.status_code == 422:
            raise AnnotationValidationError("semantic_annotator_invalid_request", resp.text)
        if resp.status_code == 503:
            raise AnnotationUnavailableError("semantic_annotator_unavailable", resp.text)
        if resp.status_code >= 500:
            raise AnnotationBackendError("semantic_annotator_backend_error", resp.text)
        if resp.status_code != 200:
            raise AnnotationBackendError(
                "semantic_annotator_unexpected_status",
                f"Unexpected status {resp.status_code}: {resp.text}",
            )

        try:
            body = resp.json()
            return _parse_annotation(body)
        except (ValueError, KeyError, TypeError) as exc:
            # Fail Fast: a 200 response that doesn't match the expected
            # AnnotationResult shape is a contract violation, not
            # something to paper over with a zero-vector default.
            raise AnnotationBackendError(
                "semantic_annotator_schema_mismatch",
                f"Semantic Annotator response did not match the expected "
                f"AnnotationResult shape: {exc}",
            ) from exc
