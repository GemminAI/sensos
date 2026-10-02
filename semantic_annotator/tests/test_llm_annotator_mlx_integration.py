"""End-to-end (mocked mlx_lm) integration test: LLMAnnotator ->
MLXRuntimeBridge -> Harmony extraction -> AnnotatedObservation.

Confirms the existing `LLMAnnotator`/`Annotation` contract is reused
unchanged -- `harmony.py`'s extraction is the only new code in this
path -- and that a Harmony-formatted GPT-OSS response, once its 'final'
channel is extracted, produces a schema-conformant `AnnotatedObservation`
exactly as a well-behaved `VLLMRuntimeBridge` response would.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from semantic_annotator.llm_annotator import LLMAnnotator
from semantic_annotator.mlx_runtime_bridge import MLXRuntimeBridge
from semantic_annotator.models import Observation


@dataclass
class _FakeResponse:
    text: str
    prompt_tokens: int
    generation_tokens: int


class _FakeTokenizer:
    def apply_chat_template(
        self, messages: list[dict[str, str]], add_generation_prompt: bool
    ) -> list[int]:
        return [1, 2, 3]


_HARMONY_CHUNKS = [
    "<|channel|>analysis<|message|>The input describes a market event; "
    "produce annotation labels.<|end|>",
    "<|start|>assistant<|channel|>final<|message|>",
    '[{"label":"StockMarketCrash","confidence":0.9,"taxonomy":"FinancialEvent"},'
    '{"label":"InvestorPanic","confidence":0.8,"taxonomy":"InvestorEmotion"}]',
]


def test_llm_annotator_produces_annotated_observation_via_mlx_harmony_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_load(model_path: str) -> tuple[object, _FakeTokenizer]:
        return object(), _FakeTokenizer()

    def fake_stream_generate(*args: Any, **kwargs: Any) -> Any:
        for chunk in _HARMONY_CHUNKS:
            yield _FakeResponse(text=chunk, prompt_tokens=85, generation_tokens=1)

    fake_module = types.ModuleType("mlx_lm")
    fake_module.load = fake_load  # type: ignore[attr-defined]
    fake_module.stream_generate = fake_stream_generate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_module)

    bridge = MLXRuntimeBridge(model_path="mlx-community/gpt-oss-20b-MXFP4-Q4")
    annotator = LLMAnnotator(bridge)

    observation = Observation(
        id="obs-1",
        source="test-sensor",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        payload={
            "text": "The stock market crashed today, causing widespread panic among investors."
        },
    )

    annotated = annotator.annotate(observation)

    assert annotated.observation is observation
    assert [a.label for a in annotated.annotations] == ["StockMarketCrash", "InvestorPanic"]
    assert annotated.annotations[0].confidence == 0.9
    assert annotated.annotations[0].taxonomy == "FinancialEvent"
    assert annotated.annotations[1].label == "InvestorPanic"
    assert 0.0 <= annotated.annotations[0].confidence <= 1.0
    assert 0.0 <= annotated.annotations[1].confidence <= 1.0
