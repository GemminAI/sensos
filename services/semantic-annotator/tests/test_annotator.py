import json

import pytest

from app.annotator import annotate_text, get_provider, normalize_provider
from app.schemas import Annotation

_FAKE_RAW_RESPONSE = json.dumps({
    "tags": {
        "T09_strategic_interest_vector": {"security": 0.1, "economy": 0.2, "technology": 0.0, "resources": 0.0, "ideology": 0.0, "environment": 0.0},
        "T10_epistemic_confidence": 0.85,
        "T19_conflict_factuality_index": 0.05,
    },
    "subject": {"primary": "Tokyo", "type": "location", "description": "capital of Japan"},
    "entities": [{"text": "Tokyo", "type": "location"}],
    "events": [],
    "time": {"tense": "present"},
    "location": {"primary": "Tokyo", "type": "city"},
})


class _FakeBackend:
    name = "anthropic"

    @property
    def model_name(self) -> str:
        return "fake-model-v1"

    def annotate_raw(self, text: str) -> str:
        return _FAKE_RAW_RESPONSE


@pytest.mark.parametrize("alias,expected", [
    ("anthropic", "anthropic"), ("claude", "anthropic"),
    ("openai", "openai"), ("gpt", "openai"),
    ("gemini", "gemini"), ("google", "gemini"),
    ("ANTHROPIC", "anthropic"),
])
def test_normalize_provider_aliases(alias, expected):
    assert normalize_provider(alias) == expected


def test_normalize_provider_rejects_unknown():
    with pytest.raises(ValueError):
        normalize_provider("not-a-provider")


def test_get_provider_raises_runtime_error_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        get_provider("anthropic")


def test_annotate_text_rejects_empty_text():
    with pytest.raises(ValueError, match="text must not be empty"):
        annotate_text("   ", "anthropic")


def test_annotate_text_fans_out_into_well_formed_annotation(monkeypatch):
    monkeypatch.setattr("app.annotator.get_provider", lambda provider: _FakeBackend())

    result = annotate_text("The capital of Japan is Tokyo.", "anthropic")

    # Round-trips through the pydantic schema without error.
    annotation = Annotation.model_validate(result)
    assert annotation.version == "1.0"
    assert annotation.tags.T10_epistemic_confidence == 0.85
    assert annotation.subject.primary == "Tokyo"
    assert annotation.entities[0].text == "Tokyo"
    assert annotation.events == []
    assert annotation.time.tense == "present"
    assert annotation.location.primary == "Tokyo"
    assert annotation.reference is None
    assert annotation.interpreter is None
    assert annotation.metadata.provider == "anthropic"
    assert annotation.metadata.model == "fake-model-v1"
    assert annotation.confidence.overall.value == 0.85
