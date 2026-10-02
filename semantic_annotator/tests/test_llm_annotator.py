import json

import pytest

from semantic_annotator.llm_annotator import (
    LLMAnnotator,
    LLMResponseNotJSONError,
    LLMSchemaViolationError,
)
from semantic_annotator.models import Observation
from semantic_annotator.runtime_bridge import CompletionResult


class FakeRuntimeBridge:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_call: dict[str, str] | None = None

    def complete(self, *, system_prompt: str, user_prompt: str) -> CompletionResult:
        self.last_call = {"system_prompt": system_prompt, "user_prompt": user_prompt}
        return CompletionResult(content=self.response, prompt_tokens=0, completion_tokens=0)


def test_llm_annotator_parses_valid_json_response(observation: Observation) -> None:
    bridge = FakeRuntimeBridge(
        json.dumps([{"label": "animal", "confidence": 0.9, "taxonomy": "35tag:animal"}])
    )

    result = LLMAnnotator(bridge).annotate(observation)

    assert result.observation is observation
    assert [a.label for a in result.annotations] == ["animal"]
    assert result.annotations[0].confidence == 0.9
    assert result.annotations[0].taxonomy == "35tag:animal"


def test_llm_annotator_accepts_empty_array(observation: Observation) -> None:
    bridge = FakeRuntimeBridge("[]")

    result = LLMAnnotator(bridge).annotate(observation)

    assert result.annotations == ()


def test_llm_annotator_passes_payload_text_to_bridge(observation: Observation) -> None:
    bridge = FakeRuntimeBridge("[]")

    LLMAnnotator(bridge).annotate(observation)

    assert bridge.last_call is not None
    assert bridge.last_call["user_prompt"] == observation.payload["text"]


def test_llm_annotator_rejects_malformed_json(observation: Observation) -> None:
    bridge = FakeRuntimeBridge("not json")

    with pytest.raises(LLMResponseNotJSONError):
        LLMAnnotator(bridge).annotate(observation)


def test_llm_annotator_rejects_non_array_json(observation: Observation) -> None:
    bridge = FakeRuntimeBridge(json.dumps({"label": "animal", "confidence": 0.9}))

    with pytest.raises(LLMSchemaViolationError):
        LLMAnnotator(bridge).annotate(observation)


def test_llm_annotator_rejects_missing_required_field(observation: Observation) -> None:
    bridge = FakeRuntimeBridge(json.dumps([{"label": "animal"}]))

    with pytest.raises(LLMSchemaViolationError):
        LLMAnnotator(bridge).annotate(observation)


def test_llm_annotator_rejects_out_of_range_confidence(observation: Observation) -> None:
    bridge = FakeRuntimeBridge(json.dumps([{"label": "animal", "confidence": 1.5}]))

    with pytest.raises(LLMSchemaViolationError):
        LLMAnnotator(bridge).annotate(observation)
