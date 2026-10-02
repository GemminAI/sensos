"""Unit tests for MLXRuntimeBridge.

`mlx_lm` is not installed in this environment (an optional, Apple-
Silicon-only extra -- see pyproject.toml's `[project.optional-
dependencies] mlx`), so these tests either exercise the real
ImportError path directly, or inject a fake `mlx_lm` module via
`sys.modules` before calling `complete()` -- mirroring how
`test_runtime_bridge.py` monkeypatches `urllib.request.urlopen` instead
of requiring a live vLLM server.
"""

from __future__ import annotations

import ast
import sys
import types
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from semantic_annotator.mlx_runtime_bridge import MLXRuntimeBridge
from semantic_annotator.runtime_bridge import CompletionResult, RuntimeBridge, RuntimeBridgeError

_SRC_DIR = Path(__file__).resolve().parent.parent / "src" / "semantic_annotator"
MODULE_PATH = _SRC_DIR / "mlx_runtime_bridge.py"


@dataclass
class _FakeResponse:
    text: str
    prompt_tokens: int
    generation_tokens: int


class _FakeTokenizer:
    def __init__(self, calls: dict[str, Any]) -> None:
        self._calls = calls

    def apply_chat_template(
        self, messages: list[dict[str, str]], add_generation_prompt: bool
    ) -> list[int]:
        self._calls["chat_template_messages"] = messages
        self._calls["chat_template_add_generation_prompt"] = add_generation_prompt
        return [1, 2, 3]


def _install_fake_mlx_lm(
    monkeypatch: pytest.MonkeyPatch, *, load: Any, stream_generate: Any
) -> None:
    fake_module = types.ModuleType("mlx_lm")
    fake_module.load = load  # type: ignore[attr-defined]
    fake_module.stream_generate = stream_generate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_module)


# -- Structural contract -----------------------------------------------------


def test_mlx_runtime_bridge_never_imports_mlx_lm_at_module_level() -> None:
    """mlx_lm must be imported lazily so semantic_annotator (and its test
    suite) stay importable without MLX installed -- mirrors
    sa002_trajectory's own `test_replay_no_gpu_import_audit.py`."""
    tree = ast.parse(MODULE_PATH.read_text(), filename=str(MODULE_PATH))
    top_level_imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.add(node.module.split(".")[0])
    assert "mlx_lm" not in top_level_imports
    assert "mlx" not in top_level_imports


def test_mlx_runtime_bridge_satisfies_runtime_bridge_protocol() -> None:
    assert isinstance(MLXRuntimeBridge(model_path="mlx-community/dummy"), RuntimeBridge)


# -- Configuration ------------------------------------------------------------


def test_default_max_tokens() -> None:
    bridge = MLXRuntimeBridge(model_path="mlx-community/dummy")
    assert bridge.max_tokens == 512


def test_model_path_and_max_tokens_are_configurable() -> None:
    bridge = MLXRuntimeBridge(model_path="mlx-community/gpt-oss-20b-MXFP4-Q4", max_tokens=32)
    assert bridge.model_path == "mlx-community/gpt-oss-20b-MXFP4-Q4"
    assert bridge.max_tokens == 32


# -- mlx_lm not installed ------------------------------------------------------


def test_complete_raises_runtime_bridge_error_when_mlx_lm_is_not_installed() -> None:
    bridge = MLXRuntimeBridge(model_path="mlx-community/dummy")

    with pytest.raises(RuntimeBridgeError, match="mlx"):
        bridge.complete(system_prompt="sys", user_prompt="user")


# -- Happy path: prompt construction, generation, CompletionResult mapping ---


def test_complete_applies_chat_template_and_returns_completion_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_load(model_path: str) -> tuple[object, _FakeTokenizer]:
        calls.setdefault("load_calls", []).append(model_path)
        return object(), _FakeTokenizer(calls)

    def fake_stream_generate(
        model: object, tokenizer: object, *, prompt: list[int], max_tokens: int
    ) -> Iterator[_FakeResponse]:
        calls["stream_generate_prompt"] = prompt
        calls["stream_generate_max_tokens"] = max_tokens
        yield _FakeResponse(text="hel", prompt_tokens=7, generation_tokens=1)
        yield _FakeResponse(text="lo", prompt_tokens=7, generation_tokens=2)

    _install_fake_mlx_lm(monkeypatch, load=fake_load, stream_generate=fake_stream_generate)

    bridge = MLXRuntimeBridge(model_path="mlx-community/dummy", max_tokens=16)
    result = bridge.complete(system_prompt="you are terse", user_prompt="say hi")

    assert isinstance(result, CompletionResult)
    assert result.content == "hello"
    assert result.prompt_tokens == 7
    assert result.completion_tokens == 2

    assert calls["load_calls"] == ["mlx-community/dummy"]
    assert calls["chat_template_messages"] == [
        {"role": "system", "content": "you are terse"},
        {"role": "user", "content": "say hi"},
    ]
    assert calls["chat_template_add_generation_prompt"] is True
    assert calls["stream_generate_prompt"] == [1, 2, 3]
    assert calls["stream_generate_max_tokens"] == 16


def test_complete_reuses_loaded_model_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    def fake_load(model_path: str) -> tuple[object, _FakeTokenizer]:
        calls.setdefault("load_calls", []).append(model_path)
        return object(), _FakeTokenizer(calls)

    def fake_stream_generate(
        model: object, tokenizer: object, *, prompt: list[int], max_tokens: int
    ) -> Iterator[_FakeResponse]:
        yield _FakeResponse(text="ok", prompt_tokens=3, generation_tokens=1)

    _install_fake_mlx_lm(monkeypatch, load=fake_load, stream_generate=fake_stream_generate)

    bridge = MLXRuntimeBridge(model_path="mlx-community/dummy")
    bridge.complete(system_prompt="sys", user_prompt="one")
    bridge.complete(system_prompt="sys", user_prompt="two")

    assert calls["load_calls"] == ["mlx-community/dummy"]


# -- Error propagation ---------------------------------------------------------


def test_complete_wraps_model_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_load(model_path: str) -> tuple[object, object]:
        raise OSError("model not found")

    def fake_stream_generate(*args: Any, **kwargs: Any) -> Iterator[_FakeResponse]:
        yield from ()

    _install_fake_mlx_lm(monkeypatch, load=fake_load, stream_generate=fake_stream_generate)

    bridge = MLXRuntimeBridge(model_path="mlx-community/does-not-exist")

    with pytest.raises(RuntimeBridgeError, match="failed to load model"):
        bridge.complete(system_prompt="sys", user_prompt="user")


def test_complete_wraps_chat_template_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BrokenTokenizer:
        def apply_chat_template(self, *args: Any, **kwargs: Any) -> list[int]:
            raise ValueError("no chat template for this tokenizer")

    def fake_load(model_path: str) -> tuple[object, _BrokenTokenizer]:
        return object(), _BrokenTokenizer()

    def fake_stream_generate(*args: Any, **kwargs: Any) -> Iterator[_FakeResponse]:
        yield from ()

    _install_fake_mlx_lm(monkeypatch, load=fake_load, stream_generate=fake_stream_generate)

    bridge = MLXRuntimeBridge(model_path="mlx-community/dummy")

    with pytest.raises(RuntimeBridgeError, match="chat template"):
        bridge.complete(system_prompt="sys", user_prompt="user")


def test_complete_wraps_generation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_load(model_path: str) -> tuple[object, _FakeTokenizer]:
        return object(), _FakeTokenizer({})

    def fake_stream_generate(*args: Any, **kwargs: Any) -> Iterator[_FakeResponse]:
        raise RuntimeError("metal device error")

    _install_fake_mlx_lm(monkeypatch, load=fake_load, stream_generate=fake_stream_generate)

    bridge = MLXRuntimeBridge(model_path="mlx-community/dummy")

    with pytest.raises(RuntimeBridgeError, match="generation failed"):
        bridge.complete(system_prompt="sys", user_prompt="user")


def test_complete_raises_when_generation_yields_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_load(model_path: str) -> tuple[object, _FakeTokenizer]:
        return object(), _FakeTokenizer({})

    def fake_stream_generate(*args: Any, **kwargs: Any) -> Iterator[_FakeResponse]:
        yield from ()

    _install_fake_mlx_lm(monkeypatch, load=fake_load, stream_generate=fake_stream_generate)

    bridge = MLXRuntimeBridge(model_path="mlx-community/dummy")

    with pytest.raises(RuntimeBridgeError, match="no output"):
        bridge.complete(system_prompt="sys", user_prompt="user")


# -- Harmony (GPT-OSS) integration ---------------------------------------------
#
# Fixture text mirrors the exact shape observed from a real
# mlx-community/gpt-oss-20b-MXFP4-Q4 generation on this machine (see
# mlx_runtime_bridge.py's module docstring and harmony.py).

_HARMONY_ANALYSIS_THEN_FINAL_CHUNKS = [
    "<|channel|>analysis<|message|>thinking about labels<|end|>",
    "<|start|>assistant<|channel|>final<|message|>",
    '[{"label":"StockMarketCrash","confidence":0.9,"taxonomy":"FinancialEvent"}]',
]

_HARMONY_ANALYSIS_ONLY_CHUNKS = [
    "<|channel|>analysis<|message|>",
    "still thinking, never reached the final channel",
]


def test_complete_extracts_final_channel_from_harmony_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_load(model_path: str) -> tuple[object, _FakeTokenizer]:
        return object(), _FakeTokenizer({})

    def fake_stream_generate(*args: Any, **kwargs: Any) -> Iterator[_FakeResponse]:
        for chunk in _HARMONY_ANALYSIS_THEN_FINAL_CHUNKS:
            yield _FakeResponse(text=chunk, prompt_tokens=50, generation_tokens=1)

    _install_fake_mlx_lm(monkeypatch, load=fake_load, stream_generate=fake_stream_generate)

    bridge = MLXRuntimeBridge(model_path="mlx-community/gpt-oss-20b-MXFP4-Q4")
    result = bridge.complete(system_prompt="sys", user_prompt="user")

    expected = '[{"label":"StockMarketCrash","confidence":0.9,"taxonomy":"FinancialEvent"}]'
    assert result.content == expected
    assert "<|channel|>" not in result.content
    assert "analysis" not in result.content


def test_complete_raises_runtime_bridge_error_when_harmony_has_no_final_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_load(model_path: str) -> tuple[object, _FakeTokenizer]:
        return object(), _FakeTokenizer({})

    def fake_stream_generate(*args: Any, **kwargs: Any) -> Iterator[_FakeResponse]:
        for chunk in _HARMONY_ANALYSIS_ONLY_CHUNKS:
            yield _FakeResponse(text=chunk, prompt_tokens=50, generation_tokens=1)

    _install_fake_mlx_lm(monkeypatch, load=fake_load, stream_generate=fake_stream_generate)

    bridge = MLXRuntimeBridge(model_path="mlx-community/gpt-oss-20b-MXFP4-Q4", max_tokens=8)

    with pytest.raises(RuntimeBridgeError, match="no 'final' channel"):
        bridge.complete(system_prompt="sys", user_prompt="user")


def test_complete_passes_through_non_harmony_content_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-GPT-OSS MLX model's plain output must be completely unaffected."""

    def fake_load(model_path: str) -> tuple[object, _FakeTokenizer]:
        return object(), _FakeTokenizer({})

    def fake_stream_generate(*args: Any, **kwargs: Any) -> Iterator[_FakeResponse]:
        yield _FakeResponse(text='["ordinary"]', prompt_tokens=5, generation_tokens=1)

    _install_fake_mlx_lm(monkeypatch, load=fake_load, stream_generate=fake_stream_generate)

    bridge = MLXRuntimeBridge(model_path="mlx-community/some-other-model")
    result = bridge.complete(system_prompt="sys", user_prompt="user")

    assert result.content == '["ordinary"]'
