import json
import urllib.error
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from semantic_annotator.runtime_bridge import RuntimeBridgeError, VLLMRuntimeBridge


@contextmanager
def _fake_response(body: bytes) -> Iterator[Any]:
    class _Response:
        def read(self) -> bytes:
            return body

    yield _Response()


def _openai_response(content: str, prompt_tokens: int = 12, completion_tokens: int = 3) -> bytes:
    return json.dumps(
        {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        }
    ).encode("utf-8")


def _bridge() -> VLLMRuntimeBridge:
    return VLLMRuntimeBridge(base_url="http://vllm:8000", model="test-model")


def test_complete_returns_message_content_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **kw: _fake_response(_openai_response("hello")),
    )

    result = _bridge().complete(system_prompt="sys", user_prompt="user")

    assert result.content == "hello"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 3


def test_complete_wraps_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*a: object, **kw: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise)

    with pytest.raises(RuntimeBridgeError):
        _bridge().complete(system_prompt="sys", user_prompt="user")


def test_complete_wraps_malformed_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **kw: _fake_response(b"not json"),
    )

    with pytest.raises(RuntimeBridgeError):
        _bridge().complete(system_prompt="sys", user_prompt="user")


def test_complete_wraps_unexpected_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **kw: _fake_response(json.dumps({"unexpected": "shape"}).encode("utf-8")),
    )

    with pytest.raises(RuntimeBridgeError):
        _bridge().complete(system_prompt="sys", user_prompt="user")
