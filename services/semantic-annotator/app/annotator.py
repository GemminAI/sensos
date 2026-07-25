"""Orchestration - Settings, backend registry, and annotate_text(), the
single entry point that turns raw text into a full Annotation dict (see
app/schemas.py::Annotation).

One backend call per request; app/tags.py, subject.py, entities.py,
events.py, temporal.py and location.py each parse their own slice of the
same JSON response - no separate call per field group.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.entities import parse_entities
from app.events import parse_events
from app.location import parse_location
from app.schemas import ANNOTATION_SCHEMA_VERSION
from app.subject import parse_subject
from app.tags import extract_json_object, parse_tags
from app.temporal import parse_time
from backends.anthropic_provider import AnthropicProvider
from backends.base import BaseAnnotatorProvider
from backends.gemini_provider import GeminiProvider
from backends.openai_provider import OpenAIProvider
from common.confidence import build_confidence
from common.metadata import build_metadata

SUPPORTED_PROVIDERS = ("anthropic", "openai", "gemini")

_PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "openai": "openai",
    "gpt": "openai",
    "gemini": "gemini",
    "google": "gemini",
}

_PROVIDER_CLASSES: dict[str, type[BaseAnnotatorProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 8011
    anthropic_model: str = "claude-haiku-4-5-20251001"
    openai_model: str = "gpt-4o-mini"
    gemini_model: str = "gemini-2.0-flash"
    request_timeout_seconds: int = 60

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.environ.get("SEMANTIC_ANNOTATOR_HOST", "0.0.0.0"),
            port=int(os.environ.get("SEMANTIC_ANNOTATOR_PORT", "8011")),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            request_timeout_seconds=int(os.environ.get("SEMANTIC_ANNOTATOR_TIMEOUT", "60")),
        )

    def api_key_for(self, provider: str) -> str | None:
        keys = {
            "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
            "openai": os.environ.get("OPENAI_API_KEY"),
            "gemini": os.environ.get("GEMINI_API_KEY"),
        }
        return keys.get(provider)

    def model_for(self, provider: str) -> str:
        models = {
            "anthropic": self.anthropic_model,
            "openai": self.openai_model,
            "gemini": self.gemini_model,
        }
        return models[provider]


settings = Settings.from_env()


def normalize_provider(provider: str) -> str:
    key = provider.strip().lower()
    if key not in _PROVIDER_ALIASES:
        supported = ", ".join(SUPPORTED_PROVIDERS)
        raise ValueError(f"Unknown provider {provider!r}. Choose: {supported}")
    return _PROVIDER_ALIASES[key]


def get_provider(provider: str) -> BaseAnnotatorProvider:
    canonical = normalize_provider(provider)
    api_key = settings.api_key_for(canonical)
    if not api_key:
        raise RuntimeError(f"{canonical.upper()}_API_KEY is not set")
    provider_cls = _PROVIDER_CLASSES[canonical]
    return provider_cls(
        api_key=api_key,
        model=settings.model_for(canonical),
        timeout=settings.request_timeout_seconds,
    )


def annotate_text(text: str, provider: str) -> dict[str, Any]:
    """Produce a full Annotation dict from raw text using the requested
    backend. Raises ValueError for bad input/malformed backend output,
    RuntimeError for backend/transport failures (including a missing API
    key) - callers (api/server.py) map these to 422 / 502 / 503."""
    if not text or not text.strip():
        raise ValueError("text must not be empty")

    backend = get_provider(provider)
    raw = backend.annotate_raw(text)
    data = extract_json_object(raw)

    tags = parse_tags(data)
    subject = parse_subject(data)
    entities = parse_entities(data)
    events = parse_events(data)
    time_block = parse_time(data)
    location = parse_location(data)
    metadata = build_metadata(text=text, provider=backend.name, model=backend.model_name)
    confidence = build_confidence(data, tags=tags, subject=subject, time=time_block, location=location)

    return {
        "version": ANNOTATION_SCHEMA_VERSION,
        "tags": tags,
        "subject": subject,
        "entities": entities,
        "events": events,
        "time": time_block,
        "location": location,
        "reference": None,
        "interpreter": None,
        "metadata": metadata,
        "confidence": confidence,
    }
