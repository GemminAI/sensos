"""RuntimeBridge: confines the non-determinism of a real LLM call.

Per the original EXP-5100 constitution's Pillar 2 ("Strict Confinement of
Semantic Non-Determinism"), everything about talking to a real inference
server -- HTTP transport, timeouts, malformed responses, API drift -- is
walled off behind this module. Nothing outside it constructs a raw HTTP
request to an LLM backend. Since Annotation is semantic-annotator's own
responsibility (RFC-OBS000 / AMS-0001), this boundary now lives here
rather than in EXP-5100.

Implemented with the standard library only (no `httpx`/`requests`), to
preserve semantic-annotator's zero-runtime-dependency property
(`pyproject.toml` `dependencies = []`).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class RuntimeBridgeError(Exception):
    """Raised when a RuntimeBridge call fails: timeout, transport error,
    non-2xx response, or a response that doesn't match the expected
    OpenAI-compatible API shape. Never a raw urllib/socket exception."""


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """A single RuntimeBridge call's result: the raw text plus token usage.

    Token counts are carried here (not re-derived elsewhere) because the
    RuntimeBridge is the only place with access to the raw API response --
    per Pillar 2, no caller may make its own HTTP call to recover them
    (e.g. for the handoff's §7 Token Efficiency metric)."""

    content: str
    prompt_tokens: int
    completion_tokens: int


@runtime_checkable
class RuntimeBridge(Protocol):
    """Anything that can turn a prompt into an LLM completion.

    Concrete bridges (vLLM/OpenAI-compatible HTTP today; others later)
    implement this protocol. Callers (e.g. LLMAnnotator) depend only on
    this interface, never on a specific transport -- mirroring how
    `pipeline`/`cli` depend only on the `Annotator` protocol.
    """

    def complete(self, *, system_prompt: str, user_prompt: str) -> CompletionResult: ...


@dataclass(frozen=True, slots=True)
class VLLMRuntimeBridge:
    """RuntimeBridge backed by a vLLM OpenAI-compatible HTTP server.

    `temperature` defaults to 0 (greedy decoding) per SA001's determinism
    goal (handoff §6/§7) -- callers pursuing a different tradeoff may
    override it explicitly.
    """

    base_url: str
    model: str
    timeout_s: float = 30.0
    temperature: float = 0.0
    max_tokens: int = 512

    def complete(self, *, system_prompt: str, user_prompt: str) -> CompletionResult:
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/v1/chat/completions",
            data=json.dumps(request_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeBridgeError(f"RuntimeBridge transport failure: {exc}") from exc

        try:
            parsed = json.loads(raw)
            usage = parsed.get("usage", {})
            return CompletionResult(
                content=str(parsed["choices"][0]["message"]["content"]),
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            )
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeBridgeError(
                f"RuntimeBridge received a malformed API response: {exc}"
            ) from exc
