"""Tests for runtime/services/semantic_annotator_client.py - the sole
Runtime-side boundary to the Semantic Annotator service.

No real network calls: httpx.AsyncClient.get/post are patched to return
real httpx.Response objects (not mocks) built in-process, so response
parsing (resp.json(), resp.text, resp.raise_for_status()) exercises real
httpx behavior.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from runtime.core.exceptions import (
    AnnotationBackendError,
    AnnotationUnavailableError,
    AnnotationValidationError,
)
from runtime.services.semantic_annotator_client import (
    AnnotationResult,
    SemanticAnnotatorClient,
)

WELL_FORMED_BODY = {
    "version": "1.0",
    "tags": {
        "T09_strategic_interest_vector": {
            "security": 0.0, "economy": 0.0, "technology": 0.0,
            "resources": 0.0, "ideology": 0.0, "environment": 0.0,
        },
        "T10_epistemic_confidence": 0.8,
        "T19_conflict_factuality_index": 0.05,
    },
    "subject": {"primary": "Tokyo", "type": "location", "description": None},
    "entities": [],
    "events": [],
    "time": {"absolute": None, "relative": None, "tense": None},
    "location": {"primary": "Tokyo", "type": "city", "normalized": None},
    "reference": None,
    "interpreter": None,
    "metadata": {
        "annotation_id": "x", "created_at": "2026-01-01T00:00:00+00:00",
        "schema_version": "1.0", "engine": "semantic-annotator",
        "engine_version": "1.0.0", "provider": "anthropic", "model": "m",
        "input_length": 5,
    },
    "confidence": {
        "overall": {"value": 0.8, "quality": "REAL", "reason": None},
        "tags": {},
        "subject": {"value": None, "quality": "REAL", "reason": None},
        "entities": {"value": None, "quality": "PLACEHOLDER", "reason": None},
        "events": {"value": None, "quality": "PLACEHOLDER", "reason": None},
        "time": {"value": None, "quality": "PLACEHOLDER", "reason": None},
        "location": {"value": None, "quality": "REAL", "reason": None},
    },
}


def _client() -> SemanticAnnotatorClient:
    return SemanticAnnotatorClient(base_url="http://fake-semantic-annotator:8011")


def _patch_post(response: httpx.Response):
    return patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=response))


def _patch_get(response: httpx.Response):
    return patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=response))


def _response(status_code: int, body: dict, method: str = "POST", path: str = "/annotate") -> httpx.Response:
    return httpx.Response(status_code, json=body, request=httpx.Request(method, f"http://x{path}"))


# ── POST /annotate -> AnnotationResult ──────────────────────────────────

@pytest.mark.asyncio
async def test_annotate_success_returns_annotation_result():
    with _patch_post(_response(200, WELL_FORMED_BODY)):
        result = await _client().annotate("The capital of Japan is Tokyo.")
    assert isinstance(result, AnnotationResult)
    assert result.tags.t10_epistemic_confidence == 0.8
    assert result.subject == {"primary": "Tokyo", "type": "location", "description": None}
    assert result.entities == []


@pytest.mark.asyncio
async def test_annotate_never_receives_a_provider_selection():
    """Runtime must not know which backend Semantic Annotator uses -
    annotate() takes no provider argument at all."""
    import inspect

    sig = inspect.signature(SemanticAnnotatorClient.annotate)
    assert "provider" not in sig.parameters


# ── Error Contract: HTTP status -> Runtime exception ────────────────────

@pytest.mark.asyncio
async def test_annotate_422_raises_annotation_validation_error():
    with _patch_post(_response(422, {"detail": "text must not be empty"})):
        with pytest.raises(AnnotationValidationError):
            await _client().annotate("")


@pytest.mark.asyncio
async def test_annotate_503_raises_annotation_unavailable_error():
    with _patch_post(_response(503, {"detail": "ANTHROPIC_API_KEY is not set"})):
        with pytest.raises(AnnotationUnavailableError):
            await _client().annotate("hello")


@pytest.mark.asyncio
async def test_annotate_502_raises_annotation_backend_error():
    with _patch_post(_response(502, {"detail": "upstream 500"})):
        with pytest.raises(AnnotationBackendError):
            await _client().annotate("hello")


@pytest.mark.asyncio
async def test_annotate_connection_failure_raises_annotation_unavailable_error():
    with patch.object(httpx.AsyncClient, "post", AsyncMock(side_effect=httpx.ConnectError("refused"))):
        with pytest.raises(AnnotationUnavailableError):
            await _client().annotate("hello")


# ── Fail Fast: malformed 200 body must raise, never silently default ───

@pytest.mark.asyncio
async def test_annotate_missing_mandatory_tag_fails_fast():
    broken_body = dict(WELL_FORMED_BODY)
    broken_body["tags"] = {"T10_epistemic_confidence": 0.8}  # T09/T19 missing
    with _patch_post(_response(200, broken_body)):
        with pytest.raises(AnnotationBackendError, match="AnnotationResult shape"):
            await _client().annotate("hello")


@pytest.mark.asyncio
async def test_annotate_missing_top_level_key_fails_fast():
    broken_body = {k: v for k, v in WELL_FORMED_BODY.items() if k != "metadata"}
    with _patch_post(_response(200, broken_body)):
        with pytest.raises(AnnotationBackendError, match="AnnotationResult shape"):
            await _client().annotate("hello")


@pytest.mark.asyncio
async def test_annotate_result_never_carries_a_zero_vector_fallback():
    """Regression guard against the exact anti-pattern Fail Fast replaces:
    a malformed response must raise, not quietly resolve to [0,0,0,0,0,0]."""
    broken_body = dict(WELL_FORMED_BODY)
    broken_body["tags"] = {}  # all tag fields missing
    with _patch_post(_response(200, broken_body)):
        with pytest.raises(AnnotationBackendError):
            await _client().annotate("hello")


# ── Version Negotiation ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_version_compatibility_accepts_known_schema_version():
    body = {"engine": "semantic-annotator", "engine_version": "1.0.0", "schema_version": "1.0"}
    with _patch_get(_response(200, body, method="GET", path="/version")):
        await _client().check_version_compatibility()  # must not raise


@pytest.mark.asyncio
async def test_check_version_compatibility_rejects_unknown_schema_version():
    body = {"engine": "semantic-annotator", "engine_version": "2.0.0", "schema_version": "2.0"}
    with _patch_get(_response(200, body, method="GET", path="/version")):
        with pytest.raises(AnnotationBackendError, match="schema_version"):
            await _client().check_version_compatibility()


@pytest.mark.asyncio
async def test_check_version_compatibility_unreachable_raises_unavailable_error():
    with patch.object(httpx.AsyncClient, "get", AsyncMock(side_effect=httpx.ConnectError("refused"))):
        with pytest.raises(AnnotationUnavailableError):
            await _client().check_version_compatibility()


# ── health() ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_true_on_200():
    with _patch_get(_response(200, {"status": "ok"}, method="GET", path="/health")):
        assert await _client().health() is True


@pytest.mark.asyncio
async def test_health_false_on_connection_error():
    with patch.object(httpx.AsyncClient, "get", AsyncMock(side_effect=httpx.ConnectError("refused"))):
        assert await _client().health() is False
