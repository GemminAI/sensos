"""Llama-3.1-8B-Instruct on MLX (4bit) that also returns the hidden state behind every token (WP1b).

``Llama31MLXProvider`` hands the whole loop to ``mlx_lm.stream_generate``, which does not expose
hidden states. This provider runs the same loop itself -- the same prefill of ``prompt[:-1]``, then one
token per step with the KV cache, the same ``logprobs = logits - logsumexp(logits)``, and the same
``HFOrderSampler`` -- and keeps ``model.model(...)[0, -1, :]`` at every step.

Row rule (the contract's ``rule_id_basis``): row ``i`` is the last-position state of the step that
decided ``token_ids[i]``. Row 0 is therefore the state at the last prompt position (``n_in - 1``), row
``i`` the state at the position of ``token_ids[i-1]``. The step that decides EOS contributes neither a
row nor a token id. The last token id has no row (it was never fed to the model).

``mlx_lm``'s ``LlamaModel.__call__`` returns ``self.norm(h)``: the state is the output of the final
RMSNorm (HF's ``hidden_states[-1]`` is that same point), not the residual stream before it.

This is MLX-4bit arithmetic. It is not the CUDA-bf16 measurement space of the MSD0001 / TRJ003 data and
must not be compared with it or used to calibrate against it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from sensos_inference.inference import (
    EOS_MISSING,
    GENERATE_FAILED,
    LENGTH_LIMIT,
    LOAD_FAILED,
)
from sensos_inference.providers.llama31_mlx import DEFAULT_MODEL_ID, Llama31MLXProvider
from sensos_inference.sampling import HFOrderSampler

HIDDEN_DIMENSION = 4096
PREFILL_STEP_SIZE = 2048  # mlx_lm.generate_step's default

ROW_RULE = (
    "row i = last-position output of model.model (after the final RMSNorm) in the step that decided "
    "token_ids[i]; row 0 is the state at the last prompt position; the step that decides EOS gives no "
    "row and no token id; the last token id has no row"
)

#: Tokenizer files that enter ``tokenizer_sha256``, if present.
TOKENIZER_FILES = ("special_tokens_map.json", "tokenizer.json", "tokenizer_config.json")


# ---- hashing rules -----------------------------------------------------------------------------


def _hash_files(paths: Sequence[Path]) -> str:
    """SHA-256 over ``name`` + NUL + content + NUL for each file, in ascending file-name order."""
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.name):
        digest.update(path.name.encode("utf-8") + b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 24), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def tokenizer_sha256(snapshot: Path) -> str | None:
    """Rule: the files of ``TOKENIZER_FILES`` that exist in the model snapshot, hashed by ``_hash_files``
    (ascending file-name order, name + content). ``None`` when none of them exists."""
    present = [snapshot / name for name in TOKENIZER_FILES if (snapshot / name).is_file()]
    return _hash_files(present) if present else None


def weights_sha256(snapshot: Path, cache_dir: Path | None = None) -> str | None:
    """Rule: every ``*.safetensors`` in the model snapshot, hashed by ``_hash_files`` (ascending
    file-name order, name + content). The result is cached in a per-model file under ``cache_dir``
    (default ``~/.sensos/model_hashes``, outside ``~/.cache``), keyed by file names, sizes and mtimes."""
    files = sorted(snapshot.glob("*.safetensors"), key=lambda p: p.name)
    if not files:
        return None
    stamp = [[p.name, p.stat().st_size, p.stat().st_mtime_ns] for p in files]
    directory = cache_dir or Path.home() / ".sensos" / "model_hashes"
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", str(snapshot.resolve()))
    cache_file = directory / f"{key}.json"
    try:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("files") == stamp and isinstance(cached.get("weights_sha256"), str):
            return str(cached["weights_sha256"])
    except (OSError, ValueError):
        pass
    value = _hash_files(files)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"files": stamp, "weights_sha256": value}), encoding="utf-8")
    except OSError:
        pass  # the cache is a convenience
    return value


def tokenizer_special_ids(tokenizer: Any) -> list[int]:
    """The ids the tokenizer marks special: ``all_special_ids`` plus every added token with
    ``special=True`` (the Llama 3 header and ``<|eot_id|>`` tokens are of the second kind)."""
    ids: set[int] = {int(i) for i in (getattr(tokenizer, "all_special_ids", None) or [])}
    decoder = getattr(tokenizer, "added_tokens_decoder", None)
    if decoder:
        ids |= {int(i) for i, token in decoder.items() if getattr(token, "special", False)}
    return sorted(ids)


def special_tokens_in(prompt_ids: Sequence[int], special_ids: Sequence[int]) -> list[list[int]]:
    """Rule: the prompt ids that are special ids, as ``[position, id]`` pairs in ascending position."""
    special = set(special_ids)
    return [[position, int(i)] for position, i in enumerate(prompt_ids) if int(i) in special]


def input_ids_sha256(ids: Sequence[int]) -> str:
    """SHA-256 of the ids as little-endian int64."""
    return hashlib.sha256(np.asarray(list(ids), dtype="<i8").tobytes()).hexdigest()


def resolve_snapshot(model_id: str, snapshot_dir: Path | None = None) -> Path | None:
    """The directory holding the model files: ``snapshot_dir``, ``model_id`` if it is a directory, or the
    newest snapshot of ``model_id`` in the Hugging Face cache. ``None`` if none exists."""
    if snapshot_dir is not None:
        return snapshot_dir
    local = Path(model_id).expanduser()
    if local.is_dir():
        return local
    root = Path(os.environ.get("HF_HUB_CACHE") or Path.home() / ".cache" / "huggingface" / "hub")
    snapshots = root / ("models--" + model_id.replace("/", "--")) / "snapshots"
    found = sorted(snapshots.glob("*"), key=lambda p: p.stat().st_mtime) if snapshots.is_dir() else []
    return found[-1] if found else None


def snapshot_revision(snapshot: Path) -> str | None:
    """The commit hash of a snapshot: the directory name in the HF cache layout, or the first line of the
    ``.cache/huggingface/download/*.metadata`` files of a ``huggingface-cli download --local-dir`` copy
    (only when they all agree)."""
    if re.fullmatch(r"[0-9a-f]{40}", snapshot.name) and snapshot.parent.name == "snapshots":
        return snapshot.name
    hashes = set()
    for path in (snapshot / ".cache" / "huggingface" / "download").glob("*.metadata"):
        try:
            first = path.read_text(encoding="utf-8").splitlines()[0].strip()
        except (OSError, IndexError):
            continue
        if re.fullmatch(r"[0-9a-f]{40}", first):
            hashes.add(first)
    return hashes.pop() if len(hashes) == 1 else None


# ---- the loop ----------------------------------------------------------------------------------


class Engine(Protocol):
    """What the loop needs from a model. ``step`` feeds one token (with the KV cache) and returns the
    next-token log-probabilities ``(vocab,)`` and the last-position state ``(4096,)``."""

    def prefill(self, ids: Sequence[int]) -> None: ...

    def step(self, token: int) -> tuple[np.ndarray, np.ndarray]: ...

    @property
    def state_dtype(self) -> str: ...


def run_capture_loop(
    engine: Engine,
    prompt_ids: Sequence[int],
    sampler: Callable[[Any], int],
    eos: set[int],
    max_tokens: int,
) -> tuple[list[int], list[np.ndarray], str | None]:
    """``(token_ids, state rows, finish)``; ``finish`` is "eos", "length" or ``None`` (no tokens asked)."""
    if len(prompt_ids) == 0:
        raise ValueError("an empty prompt")
    if len(prompt_ids) > 1:
        engine.prefill(prompt_ids[:-1])
    token = int(prompt_ids[-1])
    ids: list[int] = []
    rows: list[np.ndarray] = []
    for _ in range(max_tokens):
        logprobs, state = engine.step(token)
        chosen = int(sampler(logprobs))
        if chosen in eos:
            return ids, rows, "eos"
        ids.append(chosen)
        rows.append(state)
        token = chosen
    return ids, rows, "length" if max_tokens > 0 else None


class MLXEngine:  # pragma: no cover - needs MLX and a model
    """``mlx_lm`` binding of ``Engine``, mirroring ``mlx_lm.generate.generate_step``."""

    def __init__(self, model: Any) -> None:
        import mlx.core as mx
        from mlx_lm.models.cache import make_prompt_cache

        self._mx = mx
        self._model = model
        self._cache = make_prompt_cache(model)
        self._dtype = "unknown"

    @property
    def state_dtype(self) -> str:
        return self._dtype

    def prefill(self, ids: Sequence[int]) -> None:
        mx = self._mx
        prompt = mx.array(list(ids))
        while prompt.shape[0] > 0:
            chunk = prompt[:PREFILL_STEP_SIZE]
            self._model.model(chunk[None], cache=self._cache)
            mx.eval([c.state for c in self._cache])
            prompt = prompt[PREFILL_STEP_SIZE:]
            mx.clear_cache()

    def step(self, token: int) -> tuple[np.ndarray, np.ndarray]:
        mx = self._mx
        model = self._model
        hidden = model.model(mx.array([token])[None], cache=self._cache)
        if model.args.tie_word_embeddings:  # the same expression as mlx_lm's Model.__call__
            logits = model.model.embed_tokens.as_linear(hidden)
        else:
            logits = model.lm_head(hidden)
        logits = logits[:, -1, :]
        logprobs = logits - mx.logsumexp(logits, keepdims=True)
        state = hidden[0, -1, :]
        mx.eval(logprobs, state)
        self._dtype = str(state.dtype).rsplit(".", 1)[-1]
        return (
            np.array(logprobs.astype(mx.float32)).reshape(-1),
            np.array(state.astype(mx.float32)).reshape(-1),
        )


# ---- the provider ------------------------------------------------------------------------------


@dataclass
class CaptureResult:
    """What one captured generation holds. Not an ``InferenceResult``: it carries the states and the
    items a RawObservationContract needs."""

    ok: bool
    text: str
    model_ref: str
    revision: str | None
    prompt_ids: list[int] = field(default_factory=list)
    token_ids: list[int] = field(default_factory=list)
    states: np.ndarray = field(default_factory=lambda: np.zeros((0, HIDDEN_DIMENSION), dtype=np.float32))
    state_dtype: str | None = None
    finish_reason: str | None = None
    failure_kind: str | None = None
    error: str | None = None
    chat_template_sha256: str | None = None
    tokenizer_sha256: str | None = None
    special_tokens_in: list[list[int]] | None = None
    weights_sha256: str | None = None
    mlx_version: str | None = None
    mlx_lm_version: str | None = None
    device: str | None = None
    sampler: dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 0
    load_seconds: float | None = None
    generate_seconds: float | None = None
    row_rule: str = ROW_RULE

    def summary(self) -> dict[str, Any]:
        """Everything except the arrays, JSON-able."""
        return {
            key: value
            for key, value in self.__dict__.items()
            if key not in ("states", "prompt_ids", "token_ids")
        } | {"n_in": len(self.prompt_ids), "n_gen": len(self.token_ids), "states_shape": list(self.states.shape)}


def _version(package: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(package)
    except Exception:
        return None


class Llama31MLXCaptureProvider(Llama31MLXProvider):
    name = "llama31-mlx-capture"

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        *,
        revision: str | None = None,
        loader: Callable[[str], tuple[Any, Any]] | None = None,
        engine_factory: Callable[[Any], Engine] | None = None,
        snapshot_dir: Path | None = None,
        hash_cache_dir: Path | None = None,
    ) -> None:
        super().__init__(model_id, revision=revision, loader=loader)
        self._engine_factory = engine_factory
        self._snapshot_dir = snapshot_dir
        self._hash_cache_dir = hash_cache_dir

    def _load_target(self) -> str:
        """``mlx_lm.load`` takes a path or a hub id; a local snapshot given explicitly wins."""
        return str(self._snapshot_dir) if self._snapshot_dir is not None else self.model_id

    def capture_chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_k: int = 50,
        top_p: float = 0.95,
        seed: int = 0,
    ) -> CaptureResult:
        sampler = HFOrderSampler(temperature=temperature, top_k=top_k, top_p=top_p, seed=seed)
        snapshot = resolve_snapshot(self.model_id, self._snapshot_dir)
        base: dict[str, Any] = {
            "model_ref": self.model_id,
            "revision": self.revision or (snapshot_revision(snapshot) if snapshot else None),
            "sampler": sampler.settings(),
            "max_tokens": max_tokens,
            "mlx_version": _version("mlx"),
            "mlx_lm_version": _version("mlx-lm"),
        }
        try:
            self._ensure_loaded_from(self._load_target())
        except Exception as exc:
            return CaptureResult(ok=False, text="", error=str(exc), failure_kind=LOAD_FAILED, **base)
        eos = self._eos_ids()
        base.update(
            device=self._device,
            load_seconds=self._load_seconds,
            chat_template_sha256=self.chat_template_sha256(),
            tokenizer_sha256=tokenizer_sha256(snapshot) if snapshot else None,
            weights_sha256=weights_sha256(snapshot, self._hash_cache_dir) if snapshot else None,
        )
        if not eos:
            return CaptureResult(
                ok=False, text="", error="tokenizer has no EOS token ids", failure_kind=EOS_MISSING, **base
            )
        try:
            prompt = self._tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=True)
            if hasattr(prompt, "keys") and "input_ids" in prompt:  # BatchEncoding (transformers 5)
                prompt = prompt["input_ids"]
            prompt_ids = [int(i) for i in prompt]
            base["special_tokens_in"] = special_tokens_in(prompt_ids, tokenizer_special_ids(self._tokenizer))
            engine = (self._engine_factory or MLXEngine)(self._model)
            t0 = time.perf_counter()
            ids, rows, finish = run_capture_loop(engine, prompt_ids, sampler, eos, max_tokens)
            seconds = time.perf_counter() - t0
        except Exception as exc:
            return CaptureResult(ok=False, text="", error=str(exc), failure_kind=GENERATE_FAILED, **base)
        states = (
            np.stack([np.asarray(r, dtype=np.float32) for r in rows])
            if rows
            else np.zeros((0, HIDDEN_DIMENSION), dtype=np.float32)
        )
        kind: str | None = None
        if finish == "length":
            kind = LENGTH_LIMIT
        elif finish is None:
            kind = EOS_MISSING
        return CaptureResult(
            ok=finish == "eos",
            text=self._tokenizer.decode(ids) if ids else "",
            prompt_ids=prompt_ids,
            token_ids=ids,
            states=states,
            state_dtype=engine.state_dtype,
            finish_reason=finish,
            failure_kind=kind,
            error=None if kind is None else f"generation ended without EOS ({kind})",
            generate_seconds=seconds,
            **base,
        )

    def _ensure_loaded_from(self, target: str) -> None:
        """``Llama31MLXProvider._ensure_loaded`` loads ``self.model_id``; load from ``target`` instead
        (a local snapshot) without changing the parent class."""
        original = self.model_id
        self.model_id = target
        try:
            self._ensure_loaded()
        finally:
            self.model_id = original


__all__ = [
    "ROW_RULE",
    "CaptureResult",
    "Engine",
    "Llama31MLXCaptureProvider",
    "MLXEngine",
    "input_ids_sha256",
    "resolve_snapshot",
    "run_capture_loop",
    "snapshot_revision",
    "special_tokens_in",
    "tokenizer_sha256",
    "tokenizer_special_ids",
    "weights_sha256",
]
