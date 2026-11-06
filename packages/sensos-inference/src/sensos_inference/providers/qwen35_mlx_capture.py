"""Qwen3.5 (text part of ``Qwen3_5ForConditionalGeneration``) on MLX that returns hidden states at
several capture positions behind every generated token.

Unlike ``Llama31MLXCaptureProvider`` (one position, 4096-D, 4-bit Llama) this provider

* reads the hidden size from the model config (``hidden_size``), it assumes no number;
* takes a list of ``CapturePosition`` and returns one ``[n_gen, D]`` array per position;
* runs the weights as stored (bf16 and the few float32 tensors the checkpoint holds; no quantization);
* applies a presence penalty (``PresencePenaltySampler``) the way vLLM does.

Row rule (the same as the Llama provider's): row ``i`` is the last-position state of the step that
decided ``token_ids[i]``. Row 0 is the state at the last prompt position, row ``i`` the state at the
position of ``token_ids[i-1]``. The step that decides EOS contributes neither a row nor a token id.

Positions (``CapturePosition.kind``), with ``x`` the input of decoder layer ``L``:

* ``mlp_out``    -- ``layer.mlp(post_attention_layernorm(h))``, i.e. the output of ``down_proj``,
                    where ``h = x + token_mixer(input_layernorm(x))``. The tensor the WSP edit changes.
* ``block_out``  -- ``h + mlp_out``, the residual stream after block ``L``.
* ``final_norm`` -- the output of the final RMSNorm (what ``model.model`` returns).

The model's own ``DecoderLayer`` code is not changed. For a tapped layer the engine spells out the
three lines of ``DecoderLayer.__call__`` so the intermediate value can be kept; other layers are
called as they are. ``Qwen35MLXEngine.check_equivalence`` compares this loop with the model's own
forward (it must be bit-identical).

This is MLX arithmetic on Apple GPU, not the CUDA / vLLM arithmetic of the WSP report.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from sensos_inference.inference import EOS_MISSING, GENERATE_FAILED, LENGTH_LIMIT, LOAD_FAILED
from sensos_inference.outcome import outcome as token_outcome
from sensos_inference.providers.llama31_mlx import Llama31MLXProvider
from sensos_inference.providers.llama31_mlx_capture import (
    input_ids_sha256,
    resolve_snapshot,
    snapshot_revision,
    special_tokens_in,
    tokenizer_sha256,
    tokenizer_special_ids,
    weights_sha256,
)
from sensos_inference.sampling import PresencePenaltySampler

PREFILL_STEP_SIZE = 2048

KINDS = ("mlp_out", "block_out", "final_norm")
#: ``row_rule`` names (hidden-trajectory H6 material). The same layer, two kinds = two spaces.
ROW_RULES = {
    "mlp_out": "qwen35-mlx-mlp-out/1",
    "block_out": "qwen35-mlx-block-out/1",
    "final_norm": "qwen35-mlx-final-norm/1",
}
ROW_RULE_TEXT = (
    "row i = last-position value at the capture position in the step that decided token_ids[i]; "
    "row 0 is the state at the last prompt position; the step that decides EOS gives no row and no "
    "token id; the last token id has no row"
)


@dataclass(frozen=True)
class CapturePosition:
    """Where in the network a state is read. ``layer`` is the decoder-layer index (0-based) for
    ``mlp_out`` / ``block_out`` and ``None`` for ``final_norm``."""

    kind: str
    layer: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {self.kind!r}")
        if self.kind == "final_norm":
            if self.layer is not None:
                raise ValueError("final_norm has no layer index")
        elif isinstance(self.layer, bool) or not isinstance(self.layer, int) or self.layer < 0:
            raise ValueError(f"{self.kind} needs a layer index >= 0, got {self.layer!r}")

    @property
    def name(self) -> str:
        return "final_norm" if self.kind == "final_norm" else f"L{self.layer}.{self.kind}"

    @property
    def layer_label(self) -> int | str:
        """The hidden-trajectory ``layer``: an integer, or the string ``final_norm``."""
        return "final_norm" if self.layer is None else self.layer

    @property
    def row_rule(self) -> str:
        return ROW_RULES[self.kind]


#: The five positions of the EXP-WSP-TRAJ001 pilot (the edited layers 15 and 19, and the end).
PILOT_POSITIONS = (
    CapturePosition("mlp_out", 15),
    CapturePosition("mlp_out", 19),
    CapturePosition("block_out", 15),
    CapturePosition("block_out", 19),
    CapturePosition("final_norm"),
)


def check_positions(positions: Sequence[CapturePosition], n_layers: int) -> tuple[CapturePosition, ...]:
    out = tuple(positions)
    if not out:
        raise ValueError("at least one capture position is needed")
    names = [p.name for p in out]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate capture positions: {names}")
    for p in out:
        if p.layer is not None and p.layer >= n_layers:
            raise ValueError(f"{p.name}: the model has {n_layers} layers")
    return out


class Engine(Protocol):
    """What the loop needs. ``step`` feeds one token (with the cache) and returns the next-token
    log-probabilities ``(vocab,)`` and one ``(D,)`` float32 state per position name."""

    def prefill(self, ids: Sequence[int]) -> None: ...

    def step(self, token: int) -> tuple[np.ndarray, dict[str, np.ndarray]]: ...

    @property
    def state_dtype(self) -> str: ...


def run_multi_capture_loop(
    engine: Engine,
    prompt_ids: Sequence[int],
    sampler: Callable[[Any], int],
    eos: set[int],
    max_tokens: int,
    names: Sequence[str],
) -> tuple[list[int], dict[str, list[np.ndarray]], str | None]:
    """``(token_ids, rows per position name, finish)``; ``finish`` is "eos", "length" or ``None``."""
    if len(prompt_ids) == 0:
        raise ValueError("an empty prompt")
    if len(prompt_ids) > 1:
        engine.prefill(prompt_ids[:-1])
    token = int(prompt_ids[-1])
    ids: list[int] = []
    rows: dict[str, list[np.ndarray]] = {n: [] for n in names}
    for _ in range(max_tokens):
        logprobs, states = engine.step(token)
        chosen = int(sampler(logprobs))
        if chosen in eos:
            return ids, rows, "eos"
        ids.append(chosen)
        for n in names:
            rows[n].append(states[n])
        token = chosen
    return ids, rows, "length" if max_tokens > 0 else None


class Qwen35MLXEngine:  # pragma: no cover - needs MLX and a model
    """``mlx_lm`` binding of ``Engine`` for ``mlx_lm.models.qwen3_5`` (``Model`` with
    ``language_model``)."""

    def __init__(self, model: Any, positions: Sequence[CapturePosition] = PILOT_POSITIONS) -> None:
        import mlx.core as mx
        from mlx_lm.models.base import create_attention_mask, create_ssm_mask

        self._mx = mx
        self._create_attention_mask = create_attention_mask
        self._create_ssm_mask = create_ssm_mask
        self._model = model
        self._lm = model.language_model
        self._tm = self._lm.model
        self._layers = list(self._tm.pipeline_layers)
        self.positions = check_positions(positions, len(self._layers))
        self.hidden_size = int(self._lm.args.hidden_size)
        self._by_layer: dict[int, list[CapturePosition]] = {}
        for p in self.positions:
            if p.layer is not None:
                self._by_layer.setdefault(p.layer, []).append(p)
        self._cache = model.make_cache()
        self._dtype = "unknown"

    @property
    def state_dtype(self) -> str:
        return self._dtype

    # ---- the forward pass ------------------------------------------------------------------
    def _run(self, tokens: Any, tap: bool) -> tuple[Any, dict[str, Any]]:
        tm, cache = self._tm, self._cache
        h = tm.embed_tokens(tokens)
        fa_mask = self._create_attention_mask(h, cache[tm.fa_idx]) if tm.fa_idx is not None else None
        ssm_mask = self._create_ssm_mask(h, cache[tm.ssm_idx]) if tm.ssm_idx is not None else None
        taken: dict[str, Any] = {}
        for index, (layer, c) in enumerate(zip(self._layers, cache, strict=True)):
            mask = ssm_mask if layer.is_linear else fa_mask
            wanted = self._by_layer.get(index) if tap else None
            if not wanted:
                h = layer(h, mask=mask, cache=c)
                continue
            mixer = layer.linear_attn if layer.is_linear else layer.self_attn
            mid = h + mixer(layer.input_layernorm(h), mask, c)  # = DecoderLayer's `h = x + r`
            mlp_out = layer.mlp(layer.post_attention_layernorm(mid))
            h = mid + mlp_out
            for p in wanted:
                taken[p.name] = (mlp_out if p.kind == "mlp_out" else h)[0, -1, :]
        return h, taken

    def _logits(self, final: Any) -> Any:
        if self._lm.args.tie_word_embeddings:
            return self._tm.embed_tokens.as_linear(final)
        return self._lm.lm_head(final)

    def prefill(self, ids: Sequence[int]) -> None:
        mx = self._mx
        prompt = mx.array(list(ids))
        while prompt.shape[0] > 0:
            chunk = prompt[:PREFILL_STEP_SIZE]
            self._run(chunk[None], False)
            mx.eval([c.state for c in self._cache])
            prompt = prompt[PREFILL_STEP_SIZE:]
            mx.clear_cache()

    def step(self, token: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        mx = self._mx
        h, taken = self._run(mx.array([token])[None], True)
        final = self._tm.norm(h)
        if any(p.kind == "final_norm" for p in self.positions):
            taken["final_norm"] = final[0, -1, :]
        logits = self._logits(final)[:, -1, :].astype(mx.float32)  # HF / vLLM sample from float32
        logprobs = logits - mx.logsumexp(logits, axis=-1, keepdims=True)
        ordered = [taken[p.name] for p in self.positions]
        mx.eval(logprobs, *ordered)
        self._dtype = str(ordered[0].dtype).rsplit(".", 1)[-1]
        return (
            np.array(logprobs).reshape(-1),
            {p.name: np.array(v.astype(mx.float32)).reshape(-1) for p, v in zip(self.positions, ordered, strict=True)},
        )

    # ---- self test -------------------------------------------------------------------------
    def check_equivalence(self, ids: Sequence[int]) -> dict[str, Any]:
        """Compare this loop with the model's own forward on ``ids`` (fresh caches): the final-norm
        state and the logits of the last position, and ``block_out`` of the last layer against the
        un-normalised stream. Returns max absolute differences (0.0 = bit-identical)."""
        mx = self._mx
        tokens = mx.array(list(ids))[None]
        saved = self._cache
        try:
            self._cache = self._model.make_cache()
            h, _ = self._run(tokens, True)
            mine = self._tm.norm(h)
            mine_logits = self._logits(mine)
            mx.eval(mine, mine_logits)
        finally:
            self._cache = saved
        reference = self._tm(tokens, cache=self._model.make_cache())
        ref_logits = self._logits(reference)
        mx.eval(reference, ref_logits)
        return {
            "final_norm_max_abs_diff": float(mx.max(mx.abs(mine.astype(mx.float32) - reference.astype(mx.float32)))),
            "logits_max_abs_diff": float(mx.max(mx.abs(mine_logits.astype(mx.float32) - ref_logits.astype(mx.float32)))),
        }


@dataclass
class QwenCaptureResult:
    """One captured generation. ``states[name]`` is ``[n_gen, hidden_size]`` float32."""

    ok: bool
    text: str
    model_ref: str
    revision: str | None
    hidden_size: int | None = None
    positions: list[dict[str, Any]] = field(default_factory=list)
    prompt_ids: list[int] = field(default_factory=list)
    token_ids: list[int] = field(default_factory=list)
    states: dict[str, np.ndarray] = field(default_factory=dict)
    state_dtype: str | None = None
    finish_reason: str | None = None
    failure_kind: str | None = None
    error: str | None = None
    outcome: dict[str, Any] = field(default_factory=dict)
    chat_template_sha256: str | None = None
    chat_template_kwargs: dict[str, Any] = field(default_factory=dict)
    tokenizer_sha256: str | None = None
    special_tokens_in: list[list[int]] | None = None
    prompt_ids_sha256: str | None = None
    weights_sha256: str | None = None
    eos_ids: list[int] = field(default_factory=list)
    mlx_version: str | None = None
    mlx_lm_version: str | None = None
    device: str | None = None
    sampler: dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 0
    load_seconds: float | None = None
    generate_seconds: float | None = None
    row_rule: str = ROW_RULE_TEXT

    def summary(self) -> dict[str, Any]:
        """Everything except the arrays and the id lists, JSON-able."""
        skip = ("states", "prompt_ids", "token_ids")
        out = {k: v for k, v in self.__dict__.items() if k not in skip}
        out["n_in"] = len(self.prompt_ids)
        out["n_gen"] = len(self.token_ids)
        out["states_shapes"] = {k: list(v.shape) for k, v in self.states.items()}
        return out


def _version(package: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(package)
    except Exception:
        return None


class Qwen35MLXCaptureProvider(Llama31MLXProvider):
    """Loading, EOS and chat-template helpers come from ``Llama31MLXProvider`` (unchanged)."""

    name = "qwen35-mlx-capture"

    def __init__(
        self,
        model_id: str,
        *,
        revision: str | None = None,
        loader: Callable[[str], tuple[Any, Any]] | None = None,
        engine_factory: Callable[[Any, Sequence[CapturePosition]], Engine] | None = None,
        snapshot_dir: Path | None = None,
        hash_cache_dir: Path | None = None,
    ) -> None:
        super().__init__(model_id, revision=revision, loader=loader)
        self._engine_factory = engine_factory
        self._snapshot_dir = snapshot_dir
        self._hash_cache_dir = hash_cache_dir

    def _load_target(self) -> str:
        return str(self._snapshot_dir) if self._snapshot_dir is not None else self.model_id

    def _ensure_loaded_from(self, target: str) -> None:
        original = self.model_id
        self.model_id = target
        try:
            self._ensure_loaded()
        finally:
            self.model_id = original

    def hidden_size(self) -> int | None:
        """``hidden_size`` from the loaded model's config (``None`` if it cannot be read)."""
        model = self._model
        for owner in (getattr(model, "language_model", None), model):
            args = getattr(owner, "args", None)
            value = getattr(args, "hidden_size", None)
            if isinstance(value, int):
                return value
        text = getattr(getattr(model, "args", None), "text_config", None)
        if isinstance(text, dict) and isinstance(text.get("hidden_size"), int):
            return int(text["hidden_size"])
        return None

    def _eos_ids(self) -> set[int]:
        ids = set(super()._eos_ids())
        text = getattr(getattr(self._model, "args", None), "text_config", None)
        extra = text.get("eos_token_id") if isinstance(text, dict) else None
        if isinstance(extra, int):
            ids.add(extra)
        elif isinstance(extra, list):
            ids |= {int(i) for i in extra}
        return ids

    def capture_chat(
        self,
        messages: list[dict[str, str]],
        *,
        positions: Sequence[CapturePosition] = PILOT_POSITIONS,
        max_tokens: int = 32768,
        temperature: float = 0.6,
        top_k: int = 20,
        top_p: float = 0.95,
        presence_penalty: float = 1.5,
        seed: int = 0,
        enable_thinking: bool = True,
    ) -> QwenCaptureResult:
        sampler = PresencePenaltySampler(
            temperature=temperature, top_k=top_k, top_p=top_p, seed=seed, presence_penalty=presence_penalty
        )
        snapshot = resolve_snapshot(self.model_id, self._snapshot_dir)
        template_kwargs = {"enable_thinking": enable_thinking}
        base: dict[str, Any] = {
            "model_ref": self.model_id,
            "revision": self.revision or (snapshot_revision(snapshot) if snapshot else None),
            "sampler": sampler.settings(),
            "max_tokens": max_tokens,
            "chat_template_kwargs": template_kwargs,
            "mlx_version": _version("mlx"),
            "mlx_lm_version": _version("mlx-lm"),
        }
        try:
            self._ensure_loaded_from(self._load_target())
        except Exception as exc:
            return QwenCaptureResult(ok=False, text="", error=str(exc), failure_kind=LOAD_FAILED, **base)
        eos = self._eos_ids()
        base.update(
            device=self._device,
            load_seconds=self._load_seconds,
            chat_template_sha256=self.chat_template_sha256(),
            tokenizer_sha256=tokenizer_sha256(snapshot) if snapshot else None,
            weights_sha256=weights_sha256(snapshot, self._hash_cache_dir) if snapshot else None,
            eos_ids=sorted(eos),
            hidden_size=self.hidden_size(),
        )
        if not eos:
            return QwenCaptureResult(
                ok=False, text="", error="tokenizer has no EOS token ids", failure_kind=EOS_MISSING, **base
            )
        try:
            prompt = self._tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=True, **template_kwargs
            )
            if hasattr(prompt, "keys") and "input_ids" in prompt:  # BatchEncoding (transformers 5)
                prompt = prompt["input_ids"]
            prompt_ids = [int(i) for i in prompt]
            base["special_tokens_in"] = special_tokens_in(prompt_ids, tokenizer_special_ids(self._tokenizer))
            base["prompt_ids_sha256"] = input_ids_sha256(prompt_ids)
            engine = (self._engine_factory or Qwen35MLXEngine)(self._model, positions)
            used = check_positions(positions, 10**9)
            base["positions"] = [
                {"name": p.name, "kind": p.kind, "layer": p.layer_label, "row_rule": p.row_rule}
                for p in used
            ]
            t0 = time.perf_counter()
            ids, rows, finish = run_multi_capture_loop(
                engine, prompt_ids, sampler, eos, max_tokens, [p.name for p in used]
            )
            seconds = time.perf_counter() - t0
        except Exception as exc:
            return QwenCaptureResult(ok=False, text="", error=str(exc), failure_kind=GENERATE_FAILED, **base)
        width = base["hidden_size"] or (len(next(iter(rows.values()))[0]) if ids else 0)
        states = {
            name: (np.stack([np.asarray(r, dtype=np.float32) for r in seq]) if seq else np.zeros((0, width), np.float32))
            for name, seq in rows.items()
        }
        kind: str | None = LENGTH_LIMIT if finish == "length" else (EOS_MISSING if finish is None else None)
        return QwenCaptureResult(
            ok=finish == "eos",
            text=self._tokenizer.decode(ids) if ids else "",
            prompt_ids=prompt_ids,
            token_ids=ids,
            states=states,
            state_dtype=engine.state_dtype,
            finish_reason=finish,
            failure_kind=kind,
            error=None if kind is None else f"generation ended without EOS ({kind})",
            outcome=token_outcome(ids, finish),
            generate_seconds=seconds,
            **base,
        )


__all__ = [
    "KINDS",
    "PILOT_POSITIONS",
    "ROW_RULES",
    "ROW_RULE_TEXT",
    "CapturePosition",
    "Engine",
    "Qwen35MLXCaptureProvider",
    "Qwen35MLXEngine",
    "QwenCaptureResult",
    "check_positions",
    "run_multi_capture_loop",
]
