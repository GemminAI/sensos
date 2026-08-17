"""Tests for runtime.services.semantic_anchor — fake OllamaClient for the
generation step, real MeaningMapper/MSR for the triangulation-input side
(same convention as test_meaning_triangulation.py)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from runtime.services.meaning_triangulation import run_meaning_triangulation
from runtime.services.semantic_anchor import (
    request_semantic_anchor,
    semantic_anchor_to_triangulation_input,
)


class _FakeOllama:
    def __init__(self, response_text: str = "a fixed summary", digest: str = "d" * 12, fail: bool = False):
        self.response_text = response_text
        self.digest = digest
        self._fail = fail
        self.generate_calls: list[tuple] = []

    async def generate(self, model, prompt, *, temperature, seed):
        if self._fail:
            from runtime.gateway.http_pool import RetryExhaustedError

            raise RetryExhaustedError("simulated Ollama failure")
        self.generate_calls.append((model, prompt, temperature, seed))
        return {
            "response": self.response_text,
            "done": True,
            "done_reason": "stop",
            "eval_count": 7,
            "total_duration": 42,
        }

    async def digest_of(self, model):
        return self.digest


async def test_request_semantic_anchor_builds_real_anchor():
    client = _FakeOllama(response_text="the system is stable")
    anchor = await request_semantic_anchor(
        "the system is stable and observing correctly",
        observation_id="obs-1",
        model_id="gpt-oss:20b",
        prompt_version="v1",
        client=client,
    )

    assert anchor.model_id == "gpt-oss:20b"
    assert anchor.model_revision == "d" * 12
    assert anchor.runtime == "ollama"
    assert anchor.structured_result == {"summary": "the system is stable"}
    assert anchor.provenance["source_observation_id"] == "obs-1"
    assert anchor.reproducibility["temperature"] == 0.0
    assert anchor.reproducibility["seed"] == 42
    assert len(anchor.input_hash) == 64
    assert len(anchor.anchor_id) == 64
    # prompt actually sent to the model contains the observation text
    assert "the system is stable and observing correctly" in client.generate_calls[0][1]


async def test_request_semantic_anchor_same_input_same_anchor_id():
    client = _FakeOllama(response_text="deterministic output")
    a1 = await request_semantic_anchor(
        "text", observation_id="o1", model_id="m", prompt_version="v1", client=client
    )
    a2 = await request_semantic_anchor(
        "text", observation_id="o2", model_id="m", prompt_version="v1", client=client
    )
    # anchor_id is content-addressed over (model, revision, input, prompt
    # version, output) -- observation_id is provenance, not identity, so
    # different observation_id with identical content -> identical anchor_id.
    assert a1.anchor_id == a2.anchor_id


async def test_request_semantic_anchor_unknown_prompt_version_rejected():
    client = _FakeOllama()
    with pytest.raises(ValueError):
        await request_semantic_anchor(
            "text", observation_id="o1", model_id="m", prompt_version="does-not-exist", client=client
        )


async def test_request_semantic_anchor_propagates_backend_failure():
    from runtime.gateway.http_pool import RetryExhaustedError

    client = _FakeOllama(fail=True)
    with pytest.raises(RetryExhaustedError):
        await request_semantic_anchor(
            "text", observation_id="o1", model_id="m", prompt_version="v1", client=client
        )


async def test_semantic_anchor_triangulation_input_stabilizes_and_is_deterministic():
    """The anchor's own real (fake-generated but real-shaped) text, run
    through the real MeaningMapper -> MSR chain via
    run_meaning_triangulation, must actually stabilize -- proving the
    repeated-observation construction is not just structurally valid but
    functionally sufficient."""
    client = _FakeOllama(response_text="the runtime observes a stable meaning")
    anchor = await request_semantic_anchor(
        "the runtime observes a stable meaning",
        observation_id="o1",
        model_id="m",
        prompt_version="v1",
        client=client,
    )
    anchor_input = semantic_anchor_to_triangulation_input(
        anchor, path_id="gpt_oss_anchor", base_time=datetime(2026, 8, 18, tzinfo=UTC)
    )
    assert len(anchor_input.observations) == 8
    assert anchor_input.method == "gpt_oss_semantic_anchor"

    result = run_meaning_triangulation([anchor_input], triangulation_id="t1")
    assert result.measurements[0].stabilized is True
