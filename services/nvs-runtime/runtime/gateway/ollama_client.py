"""Ollama client — the real, locally-installed inference runtime this host
actually has (Reality Audit, 2026-08-18: Ollama present and running;
MLX/mlx-lm, vLLM, and llama.cpp were all checked and are not installed).

Wire contract confirmed live against this host's own Ollama instance before
writing this module (not assumed from documentation):

    POST /api/generate {model, prompt, stream: false, options: {temperature, seed}}
      -> {model, created_at, response, done, done_reason, context,
          total_duration, load_duration, prompt_eval_count,
          prompt_eval_duration, eval_count, eval_duration}
    GET /api/tags -> {models: [{name, digest, size, ...}]}

`temperature` and `seed` were verified to actually make generation
deterministic (identical `response` across two independent calls with the
same prompt, temperature=0, seed=42) — no other sampling parameter is
claimed to be fixed here, since none other was verified.

Deliberately NOT built on `runtime.gateway.http_pool`'s shared
`NetworkProfile`: that profile's default `request_timeout_ms` is 500ms,
tuned for the fast NVS/CLE/HEKB microservice legs it was designed for
(EXP-Ubuntu011's measured WAN RTT), not for LLM generation latency, which
can legitimately take tens of seconds. This client builds its own
long-timeout `NetworkProfile` and passes it explicitly to
`request_with_retry()` on every call, reusing the same pooled-connection
transport without inheriting the wrong timeout.
"""

from __future__ import annotations

from typing import Any

from runtime.core.config import Settings, get_settings
from runtime.core.network_profile import NetworkProfile
from runtime.gateway.http_pool import RetryExhaustedError, request_with_retry

_TRANSPORT_ERRORS = (RetryExhaustedError,)

#: LLM generation profile: long timeout, no retry (retrying a slow-but-
#: working generation would just double an already-long wait; a genuine
#: failure — model not pulled, runtime down — surfaces immediately either
#: way). connect_timeout stays short: a dead Ollama process fails the TCP
#: connect fast regardless of how long generation itself might take.
_OLLAMA_PROFILE = NetworkProfile(
    mode="ollama",
    base_rtt_ms=10,
    request_timeout_ms=180_000,
    connect_timeout_ms=5_000,
    retry_count=0,
    retry_backoff_ms=0,
)


class OllamaClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def base_url(self) -> str:
        return self.settings.ollama_url

    async def health_check(self) -> bool:
        try:
            response = await request_with_retry("GET", self.base_url, "/api/tags", profile=_OLLAMA_PROFILE)
            return response.status_code == 200
        except _TRANSPORT_ERRORS:
            return False

    async def show(self, model: str) -> dict[str, Any]:
        """POST /api/show — model metadata, including `details` (family,
        parameter_size, quantization_level). Used for provenance, not
        generation."""
        response = await request_with_retry(
            "POST", self.base_url, "/api/show", json={"model": model}, profile=_OLLAMA_PROFILE
        )
        response.raise_for_status()
        return response.json()

    async def digest_of(self, model: str) -> str | None:
        """The model's content digest from GET /api/tags (a real, verifiable
        identity for `model_revision` — not a version string someone typed
        by hand). None if `model` is not present locally."""
        response = await request_with_retry("GET", self.base_url, "/api/tags", profile=_OLLAMA_PROFILE)
        response.raise_for_status()
        for entry in response.json().get("models", []):
            if entry.get("name") == model:
                return entry.get("digest")
        return None

    async def generate(
        self,
        model: str,
        prompt: str,
        *,
        temperature: float = 0.0,
        seed: int = 42,
    ) -> dict[str, Any]:
        """POST /api/generate, non-streaming. Returns the response body
        verbatim — this client does not reshape it; callers needing a
        specific field (e.g. `response`) read it themselves.

        `temperature`/`seed` are the only sampling parameters this client
        sets, because they are the only ones empirically confirmed (this
        module's docstring) to make output reproducible via this runtime.
        """
        response = await request_with_retry(
            "POST",
            self.base_url,
            "/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "seed": seed},
            },
            profile=_OLLAMA_PROFILE,
        )
        response.raise_for_status()
        return response.json()
