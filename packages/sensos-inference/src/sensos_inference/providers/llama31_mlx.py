"""Llama-3.1-8B-Instruct on MLX (4bit), for the D71 stage-2 trial.

Hidden states are NOT returned: ``mlx_lm`` does not expose them, and MLX-4bit numerics differ from
CUDA bf16 (a different measurement space). The result records what the experiment needs: text, token
ids, token counts, load/generate seconds, model_ref and revision, sampler settings, the sha256 of the
tokenizer's chat template, and why the generation ended.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Iterable
from typing import Any

from sensos_inference.inference import (
    EOS_MISSING,
    GENERATE_FAILED,
    LENGTH_LIMIT,
    LOAD_FAILED,
    InferenceResult,
)
from sensos_inference.sampling import HFOrderSampler

DEFAULT_MODEL_ID = "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit"


class Llama31MLXProvider:
    name = "llama31-mlx"

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        *,
        revision: str | None = None,
        loader: Callable[[str], tuple[Any, Any]] | None = None,
        stream: Callable[..., Iterable[Any]] | None = None,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self._loader, self._stream = loader, stream
        self._model: Any = None
        self._tokenizer: Any = None
        self._device: str | None = None
        self._load_seconds: float | None = None
        self._error: str | None = None

    # ---- loading ---------------------------------------------------------------------------
    def _default_loader(self, model_id: str) -> tuple[Any, Any]:
        from mlx_lm import load

        return load(model_id)  # type: ignore[no-any-return]

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        if self._error is not None:
            raise RuntimeError(self._error)
        t0 = time.perf_counter()
        try:
            self._model, self._tokenizer = (self._loader or self._default_loader)(self.model_id)
            try:
                import mlx.core as mx

                self._device = str(mx.default_device())
            except Exception:
                self._device = None
        except Exception as exc:
            self._error = f"load failed: {exc}"
            raise RuntimeError(self._error) from exc
        self._load_seconds = time.perf_counter() - t0

    def _eos_ids(self) -> set[int]:
        ids = getattr(self._tokenizer, "eos_token_ids", None)
        return {int(i) for i in ids} if ids else set()

    def chat_template_sha256(self) -> str | None:
        template = getattr(self._tokenizer, "chat_template", None)
        if not isinstance(template, str):
            return None
        return hashlib.sha256(template.encode("utf-8")).hexdigest()

    @staticmethod
    def _mx_sampler(sampler: Callable[[Any], int]) -> Callable[[Any], Any]:
        """``mlx_lm.generate_step`` expects an ``mx.array`` of shape (1,) back from the sampler."""
        try:
            import mlx.core as mx
        except Exception:  # no MLX (tests with a mocked stream)
            return sampler

        def wrapped(logprobs: Any) -> Any:
            return mx.array([sampler(logprobs)])

        return wrapped

    # ---- generation ------------------------------------------------------------------------
    def generate(self, prompt: str, *, max_tokens: int = 1024, **options: Any) -> InferenceResult:
        """Plain-prompt entry point (existing contract). ``options`` as in ``generate_chat``."""
        return self.generate_chat([{"role": "user", "content": prompt}], max_tokens=max_tokens, **options)

    def generate_chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_k: int = 50,
        top_p: float = 0.95,
        seed: int = 0,
    ) -> InferenceResult:
        chars = sum(len(m.get("content", "")) for m in messages)
        sampler = HFOrderSampler(temperature=temperature, top_k=top_k, top_p=top_p, seed=seed)
        base: dict[str, Any] = {
            "model": self.model_id,
            "model_ref": self.model_id,
            "revision": self.revision,
            "prompt_chars": chars,
            "max_tokens": max_tokens,
            "sampler": sampler.settings(),
        }
        try:
            self._ensure_loaded()
        except Exception as exc:
            return InferenceResult(
                ok=False, text="", error=str(exc), failure_kind=LOAD_FAILED, **base
            )
        eos = self._eos_ids()
        base.update(device=self._device, load_seconds=self._load_seconds,
                    chat_template_sha256=self.chat_template_sha256())
        if not eos:
            return InferenceResult(
                ok=False, text="", error="tokenizer has no EOS token ids", failure_kind=EOS_MISSING, **base
            )
        try:
            prompt_ids = self._tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=True
            )
            if isinstance(prompt_ids, dict):  # transformers may return a BatchEncoding
                prompt_ids = prompt_ids["input_ids"]
            stream = self._stream
            if stream is None:
                from mlx_lm import stream_generate as stream  # type: ignore[assignment]
            t0 = time.perf_counter()
            ids: list[int] = []
            finish: str | None = None
            for response in stream(  # type: ignore[misc]
                self._model,
                self._tokenizer,
                prompt=list(prompt_ids),
                max_tokens=max_tokens,
                sampler=self._mx_sampler(sampler),
            ):
                token = int(response.token)
                if token in eos:
                    finish = "eos"
                    break
                ids.append(token)
                if getattr(response, "finish_reason", None) == "length":
                    finish = "length"
            seconds = time.perf_counter() - t0
        except Exception as exc:
            return InferenceResult(
                ok=False, text="", error=str(exc), failure_kind=GENERATE_FAILED, **base
            )
        text = self._tokenizer.decode(ids) if ids else ""
        kind: str | None = None
        if finish is None:
            finish = "length" if len(ids) >= max_tokens else None
        if finish == "length":
            kind = LENGTH_LIMIT
        elif finish is None:
            kind = EOS_MISSING
        return InferenceResult(
            ok=finish == "eos",
            text=text,
            token_ids=ids,
            prompt_tokens=len(prompt_ids),
            completion_tokens=len(ids),
            generate_seconds=seconds,
            finish_reason=finish,
            failure_kind=kind,
            error=None if kind is None else f"generation ended without EOS ({kind})",
            **base,
        )
