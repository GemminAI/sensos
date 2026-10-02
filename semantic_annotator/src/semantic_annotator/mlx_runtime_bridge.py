"""MLXRuntimeBridge: a RuntimeBridge implementation backed by local MLX inference.

Per `runtime_bridge.py`'s own design intent ("Concrete bridges (vLLM/
OpenAI-compatible HTTP today; others later) implement this protocol"),
this module adds a second concrete `RuntimeBridge`: instead of an HTTP
round-trip to a vLLM server, it runs the model in-process via `mlx_lm`
on Apple Silicon (MLX/Metal). `RuntimeBridge`, `CompletionResult`, and
`RuntimeBridgeError` are reused unchanged from `runtime_bridge.py`;
`VLLMRuntimeBridge` is untouched.

`mlx_lm` is imported lazily (inside `complete()`, not at module
top-level), mirroring `sa002_trajectory.capture`'s stated rationale for
lazily importing `vllm`/`torch`: this module -- and the rest of
`semantic_annotator` -- must stay importable, and the existing test
suite must keep passing, on machines/CI without MLX installed (`mlx_lm`
ships Apple-Silicon-only wheels). Nothing outside
`MLXRuntimeBridge.complete()` needs `mlx_lm` to exist.

API confirmed against the `mlx_lm==0.31.3` install used by
`GemminAI/mac-mlx`'s own real-machine-verified smoke test
(`scripts/smoke_gpt_oss_20b.py`), not guessed from documentation:

- ``load(model_path) -> (model, tokenizer)``
- ``tokenizer.apply_chat_template(messages, add_generation_prompt=True)``
  returns a token-id list accepted directly by ``stream_generate``'s
  ``prompt`` argument.
- ``stream_generate(model, tokenizer, prompt=..., max_tokens=...)``
  yields ``GenerationResponse`` objects whose ``.text`` is a per-token
  delta (segments must be concatenated for the full completion) and
  whose ``.prompt_tokens`` / ``.generation_tokens`` are running totals
  as of that token -- so the *last* yielded response carries the final
  counts, confirmed by an actual `stream_generate` run against
  ``mlx-community/gpt-oss-20b-MXFP4-Q4``.

Some models (GPT-OSS) emit raw Harmony-formatted text instead of a
direct answer -- see `harmony.py` for why and how the 'final' channel
is extracted. Models whose output has no Harmony markers are returned
unchanged; this bridge is not GPT-OSS-specific.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from semantic_annotator.harmony import HarmonyFormatError, extract_final_channel, looks_like_harmony
from semantic_annotator.runtime_bridge import CompletionResult, RuntimeBridgeError


@dataclass(slots=True)
class MLXRuntimeBridge:
    """RuntimeBridge backed by local MLX inference (`mlx_lm`).

    Unlike `VLLMRuntimeBridge` (a stateless HTTP client), this bridge
    holds an in-process model: `model_path` is loaded once, on the
    first `complete()` call, and the loaded model/tokenizer are reused
    by subsequent calls on the same instance.
    """

    model_path: str
    max_tokens: int = 512
    _model: Any = field(default=None, init=False, repr=False, compare=False)
    _tokenizer: Any = field(default=None, init=False, repr=False, compare=False)

    def complete(self, *, system_prompt: str, user_prompt: str) -> CompletionResult:
        try:
            from mlx_lm import load, stream_generate
        except ImportError as exc:
            raise RuntimeBridgeError(
                "MLXRuntimeBridge requires the 'mlx' extra "
                "(pip install 'semantic-annotator[mlx]'); mlx_lm is not installed"
            ) from exc

        if self._model is None or self._tokenizer is None:
            try:
                # load()'s declared return type is a Union of a 2-tuple and a
                # 3-tuple (the 3rd item only appears when return_config=True,
                # which this call never passes), so at runtime this always
                # unpacks to exactly 2 values -- confirmed via mlx_lm's own
                # source, not guessed. cast() (rather than `# type: ignore`)
                # so this stays clean under mypy whether or not mlx_lm is
                # installed (with real stubs vs. the ignore_missing_imports
                # fallback, a `# type: ignore` here would be flagged as
                # unused in exactly one of those two cases).
                self._model, self._tokenizer = cast(tuple[Any, Any], load(self.model_path))
            except Exception as exc:
                raise RuntimeBridgeError(
                    f"MLXRuntimeBridge failed to load model {self.model_path!r}: {exc}"
                ) from exc

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            prompt_tokens = self._tokenizer.apply_chat_template(
                messages, add_generation_prompt=True
            )
        except Exception as exc:
            raise RuntimeBridgeError(
                f"MLXRuntimeBridge failed to apply the chat template: {exc}"
            ) from exc

        segments: list[str] = []
        last_response = None
        try:
            for response in stream_generate(
                self._model,
                self._tokenizer,
                prompt=prompt_tokens,
                max_tokens=self.max_tokens,
            ):
                segments.append(response.text)
                last_response = response
        except Exception as exc:
            raise RuntimeBridgeError(f"MLXRuntimeBridge generation failed: {exc}") from exc

        if last_response is None:
            raise RuntimeBridgeError("MLXRuntimeBridge produced no output")

        raw_content = "".join(segments)
        if looks_like_harmony(raw_content):
            try:
                content = extract_final_channel(raw_content)
            except HarmonyFormatError as exc:
                raise RuntimeBridgeError(f"MLXRuntimeBridge: {exc}") from exc
        else:
            content = raw_content

        return CompletionResult(
            content=content,
            prompt_tokens=last_response.prompt_tokens,
            completion_tokens=last_response.generation_tokens,
        )
