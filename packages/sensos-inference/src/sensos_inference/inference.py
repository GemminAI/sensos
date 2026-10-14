"""Minimal inference types.

``InferenceResult`` keeps the field names of the clean-install tree's result type
(``ok, text, model, device, prompt_chars, max_tokens, load_seconds, generate_seconds, error``) and adds
what the D71 experiment must record per generation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

#: ``failure_kind`` values (``None`` when the generation ended by EOS).
LOAD_FAILED = "load_failed"  # the model or tokenizer could not be loaded
LENGTH_LIMIT = "length_limit"  # max_tokens reached before an EOS token
EOS_MISSING = "eos_missing"  # no EOS id configured, or the stream ended with neither EOS nor the length limit
GENERATE_FAILED = "generate_failed"  # an exception during generation


@dataclass
class InferenceResult:
    ok: bool
    text: str
    model: str
    device: str | None = None
    prompt_chars: int = 0
    max_tokens: int = 0
    load_seconds: float | None = None
    generate_seconds: float | None = None
    error: str | None = None
    # ---- additions -------------------------------------------------------------------------
    token_ids: list[int] = field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    model_ref: str | None = None
    revision: str | None = None
    sampler: dict[str, Any] = field(default_factory=dict)
    chat_template_sha256: str | None = None
    finish_reason: str | None = None  # "eos" | "length" | None
    failure_kind: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class InferenceProvider(Protocol):
    name: str
    model_id: str

    def generate(self, prompt: str, *, max_tokens: int = 1024) -> InferenceResult: ...
