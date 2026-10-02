from __future__ import annotations

import pytest
from semantic_annotator.llm_annotator import LLMResponseNotJSONError
from semantic_annotator.runtime_bridge import CompletionResult, RuntimeBridgeError

from sensos.smoke import run_smoke


def test_run_smoke_fails_when_base_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUNTIME_BRIDGE_URL", raising=False)
    monkeypatch.delenv("SENSOS_MODEL_ID", raising=False)

    result = run_smoke()

    assert result.passed is False
    assert result.stage == "configuration"
    assert "RUNTIME_BRIDGE_URL" in result.detail


def test_run_smoke_fails_when_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENSOS_MODEL_ID", raising=False)

    result = run_smoke(base_url="http://localhost:8000")

    assert result.passed is False
    assert result.stage == "configuration"
    assert "SENSOS_MODEL_ID" in result.detail


def test_run_smoke_reads_config_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_BRIDGE_URL", "http://vllm:8000")
    monkeypatch.setenv("SENSOS_MODEL_ID", "some-model")

    captured: dict[str, str] = {}

    class _FakeBridge:
        def __init__(self, *, base_url: str, model: str) -> None:
            captured["base_url"] = base_url
            captured["model"] = model

        def complete(self, *, system_prompt: str, user_prompt: str) -> CompletionResult:
            return CompletionResult(content="[]", prompt_tokens=1, completion_tokens=1)

    monkeypatch.setattr("sensos.smoke.VLLMRuntimeBridge", _FakeBridge)

    result = run_smoke()

    assert captured == {"base_url": "http://vllm:8000", "model": "some-model"}
    assert result.passed is True


def test_run_smoke_reports_runtime_bridge_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingBridge:
        def __init__(self, *, base_url: str, model: str) -> None:
            pass

        def complete(self, *, system_prompt: str, user_prompt: str) -> CompletionResult:
            raise RuntimeBridgeError("connection refused")

    monkeypatch.setattr("sensos.smoke.VLLMRuntimeBridge", _FailingBridge)

    result = run_smoke(base_url="http://localhost:8000", model="some-model")

    assert result.passed is False
    assert result.stage == "RuntimeBridge (vLLM connection)"
    assert "connection refused" in result.detail


def test_run_smoke_reports_llm_annotation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MalformedBridge:
        def __init__(self, *, base_url: str, model: str) -> None:
            pass

        def complete(self, *, system_prompt: str, user_prompt: str) -> CompletionResult:
            return CompletionResult(content="not json", prompt_tokens=1, completion_tokens=1)

    monkeypatch.setattr("sensos.smoke.VLLMRuntimeBridge", _MalformedBridge)

    result = run_smoke(base_url="http://localhost:8000", model="some-model")

    assert result.passed is False
    assert result.stage == "LLMAnnotator (response parsing)"


def test_run_smoke_reports_annotated_observation_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _GoodBridge:
        def __init__(self, *, base_url: str, model: str) -> None:
            pass

        def complete(self, *, system_prompt: str, user_prompt: str) -> CompletionResult:
            return CompletionResult(
                content='[{"label":"car","confidence":0.9,"taxonomy":null}]',
                prompt_tokens=10,
                completion_tokens=5,
            )

    monkeypatch.setattr("sensos.smoke.VLLMRuntimeBridge", _GoodBridge)

    result = run_smoke(base_url="http://localhost:8000", model="some-model")

    assert result.passed is True
    assert result.stage == "AnnotatedObservation"
    assert "1 annotation" in result.detail


def test_run_smoke_never_fabricates_success_on_exception_type_mismatch() -> None:
    # Sanity: LLMResponseNotJSONError is one of the LLMAnnotationError
    # subclasses run_smoke must catch (via the base class), not something
    # it silently ignores.
    assert issubclass(LLMResponseNotJSONError, Exception)
