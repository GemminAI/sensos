"""U2 real-machine tests (T-U2-R-*). Qwen3.5 part (U2-3); the Llama part (U2-4) is a placeholder.

Real-model cases are skipped unless ``LLAMA31_SNAPSHOT`` / ``QWEN35_SNAPSHOT`` name a local
snapshot directory. Collection must not import ``mlx`` or load weights: ``mlx`` is imported only
inside the fixtures and tests, which run only with a snapshot.

The Qwen3.5 tests go through ``Qwen35MLXAdapter`` (U1's Interface). Every result is written to the
evidence record (``u2_support``; only when ``U2_EVIDENCE_DIR`` is set). Criteria are those of design
U2 v0.1 section 3: exact / bit-identical / nearest position / bit basis. No tolerance is used.
``U2_HASH_CACHE_DIR`` (optional) is the ``hash_cache_dir`` of the provider.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import resource
import subprocess
import time
from collections.abc import Iterator, Sequence
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import pytest
from u2_support import (
    DEFAULT_NOT_VERIFIED,
    ENV_LLAMA,
    ENV_QWEN,
    FIXED_PROMPTS,
    build_evidence_record,
    llama_real_machine_available,
    maybe_write_evidence,
    prompt_ids_sha256,
    qwen_real_machine_available,
    snapshot_basename,
)

ENV_HASH_CACHE = "U2_HASH_CACHE_DIR"
MODEL_BUILD_ID = "qwen3.5-0.8b-orig-r2fc06364-bf16"
COMPUTE_ENVIRONMENT = "mlx-bf16-metal"
PILOT_POINTS = ("mlp_out:15", "mlp_out:19", "block_out:15", "block_out:19", "final_norm")
GREEDY = {"top_k": 1, "seed": 0}
SEEDED = {"seed": 7}
DEFAULTS = {
    "temperature": 0.6,
    "top_k": 20,
    "top_p": 0.95,
    "presence_penalty": 1.5,
    "seed": 0,
    "enable_thinking": True,
}
PREFILL_STEP = 2048
PROMPT_IDS = ("p01", "p02", "p03", "p04")


def test_u2_fixed_prompt_set_and_not_verified_defaults() -> None:
    """Always runs: defines the fixed prompt ids and the mandatory not_verified baseline."""
    assert set(FIXED_PROMPTS) >= {"p01", "p02", "p03", "p04"}
    assert len(DEFAULT_NOT_VERIFIED) >= 1


@pytest.mark.skipif(not llama_real_machine_available(), reason=f"{ENV_LLAMA} not set")
def test_t_u2_r_llama_placeholder_requires_snapshot() -> None:
    """U2-4 will implement AC-B/C checks. This placeholder only proves the skip gate."""
    path = os.environ[ENV_LLAMA]
    assert path.strip()
    pytest.skip("U2-4 real-machine body not implemented in U2-1/U2-2")


def _messages(prompt_id: str) -> list[dict[str, str]]:
    """The fixed prompts; p04 is expanded here to a prompt of more than 2,048 tokens."""
    if prompt_id != "p04":
        return [dict(m) for m in FIXED_PROMPTS[prompt_id]]
    facts = "\n".join(f"Fact {i}: item {i} is kept in box {(i * 7) % 101}." for i in range(1, 260))
    question = "Read the facts below, then answer in one word: which box holds item 3?"
    return [{"role": "user", "content": f"{question}\n{facts}"}]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pkg(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def _peak_mb() -> float | None:
    try:
        import mlx.core as mx

        return round(mx.get_peak_memory() / 2**20, 1)
    except Exception:
        return None


def _git(*args: str) -> str:
    here = Path(__file__).resolve().parent
    try:
        out = subprocess.run(["git", *args], cwd=here, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


class Recorder:
    """Collects the checks of one run; the evidence record is written by the fixture's teardown."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.not_verified: list[str] = []

    def add(
        self,
        check_id: str,
        ac: str,
        case: str,
        *,
        input: dict[str, Any],  # noqa: A002
        output: dict[str, Any],
        compared_with: str,
        criterion: str,
        result: str,
        numbers: dict[str, Any] | None = None,
        started: float | None = None,
    ) -> None:
        nums = dict(numbers or {})
        if started is not None:
            nums["seconds"] = round(time.perf_counter() - started, 2)
        peak = _peak_mb()
        if peak is not None:
            nums["mlx_peak_memory_mb"] = peak
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        nums["process_max_rss_mb"] = round(rss / 2**20, 1)  # bytes on macOS
        self.checks.append(
            {
                "id": check_id,
                "ac": ac,
                "case": case,
                "input": input,
                "output": output,
                "compared_with": compared_with,
                "criterion": criterion,
                "result": result,
                "numbers": nums,
            }
        )


class Real:
    def __init__(self, provider: Any, adapter: Any, recorder: Recorder, snapshot: Path) -> None:
        self.provider = provider
        self.adapter = adapter
        self.rec = recorder
        self.snapshot = snapshot
        self.info: dict[str, Any] = {}

    def capture(
        self, prompt_id: str, points: Sequence[str], max_tokens: int, sampling: dict[str, Any]
    ) -> Any:
        from sensos_inference.observation import CaptureRequest

        request = CaptureRequest(points=tuple(points), max_tokens=max_tokens, sampling=dict(sampling))
        return self.adapter.capture(
            _messages(prompt_id),
            request,
            model_build_id=MODEL_BUILD_ID,
            compute_environment=COMPUTE_ENVIRONMENT,
        )

    def prompt_ids(self, prompt_id: str, thinking: bool = True) -> list[int]:
        ids = self.provider._tokenizer.apply_chat_template(
            _messages(prompt_id), add_generation_prompt=True, tokenize=True, enable_thinking=thinking
        )
        return [int(i) for i in (ids["input_ids"] if hasattr(ids, "keys") else ids)]

    def reference(
        self, prompt_id: str, sampling: dict[str, Any], max_tokens: int
    ) -> tuple[list[int], str]:
        """Generation WITHOUT capture: the model's own ``__call__`` and cache, prefill in chunks of
        2,048 as ``mlx_lm`` does, the same sampler, float32 log-softmax; nothing is tapped."""
        import mlx.core as mx
        import numpy as np

        from sensos_inference.sampling import PresencePenaltySampler

        cfg = {**DEFAULTS, **sampling}
        model, eos = self.provider._model, self.provider._eos_ids()
        sampler = PresencePenaltySampler(
            temperature=cfg["temperature"],
            top_k=cfg["top_k"],
            top_p=cfg["top_p"],
            seed=cfg["seed"],
            presence_penalty=cfg["presence_penalty"],
        )
        cache = model.make_cache()
        ids = self.prompt_ids(prompt_id, bool(cfg["enable_thinking"]))
        head = mx.array(ids[:-1])
        while head.shape[0] > 0:
            model(head[:PREFILL_STEP][None], cache=cache)
            mx.eval([c.state for c in cache])
            head = head[PREFILL_STEP:]
            mx.clear_cache()
        token, out, finish = ids[-1], [], "length"
        for _ in range(max_tokens):
            logits = model(mx.array([token])[None], cache=cache)[:, -1, :].astype(mx.float32)
            logprobs = logits - mx.logsumexp(logits, axis=-1, keepdims=True)
            mx.eval(logprobs)
            chosen = int(sampler(np.array(logprobs).reshape(-1)))
            if chosen in eos:
                finish = "eos"
                break
            out.append(chosen)
            token = chosen
        return out, finish


@pytest.fixture(scope="module")
def real() -> Iterator[Real]:
    if not qwen_real_machine_available():
        pytest.skip(f"{ENV_QWEN} not set")
    from sensos_inference.adapters import Qwen35MLXAdapter, _hardware_string
    from sensos_inference.providers.qwen35_mlx_capture import Qwen35MLXCaptureProvider

    snapshot = Path(os.environ[ENV_QWEN])
    cache_dir = os.environ.get(ENV_HASH_CACHE)
    provider = Qwen35MLXCaptureProvider(
        "qwen35-real",
        snapshot_dir=snapshot,
        hash_cache_dir=Path(cache_dir) if cache_dir else None,
    )
    provider._ensure_loaded_from(provider._load_target())
    config = json.loads((snapshot / "config.json").read_text(encoding="utf-8"))
    text = config.get("text_config", config)
    adapter = Qwen35MLXAdapter(
        provider, n_layers=int(text["num_hidden_layers"]), dimension=int(provider.hidden_size() or 0)
    )
    ctx = Real(provider, adapter, Recorder(), snapshot)
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    yield ctx
    hardware = _hardware_string()
    facts = adapter.origin_facts()["origin"]
    record = build_evidence_record(
        run_id=f"u2-qwen35-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        adapter="qwen35-mlx-capture",
        code={
            "repository": "sensos",
            "branch": _git("branch", "--show-current"),
            "commit": _git("rev-parse", "--short", "HEAD"),
            "dirty": bool(_git("status", "--porcelain", "--", ".")),
        },
        environment={
            "python": platform.python_version(),
            "mlx": _pkg("mlx"),
            "mlx_lm": _pkg("mlx-lm"),
            "transformers": _pkg("transformers"),
            "numpy": _pkg("numpy"),
        },
        model={
            "model_ref": MODEL_BUILD_ID,
            "snapshot": snapshot_basename(snapshot),
            "revision": facts["revision"],
            "weights_sha256": facts["weights_sha256"],
            "hash_source": ctx.info.get("hash_source", "unknown"),
            "quantization": facts["quantization"],
            "state_dtype": adapter.observed_state_dtype,
            "provenance": ctx.info.get("provenance"),
        },
        checks=ctx.rec.checks,
        not_verified=[
            *DEFAULT_NOT_VERIFIED,
            *sorted(set(ctx.rec.not_verified)),
            "Llama 3.1 (U2-4 not run)",
        ],
        host=hardware if isinstance(hardware, str) else "unknown",
        started_at=started,
    )
    maybe_write_evidence(record)


def _states_hash(capture: Any) -> dict[str, str]:
    import numpy as np

    return {
        name: _sha(np.ascontiguousarray(arr, dtype="<f4").tobytes())
        for name, arr in capture.states.items()
    }


def _out(capture: Any) -> dict[str, Any]:
    return {
        "n_in": capture.n_in,
        "n_gen": capture.n_gen,
        "finish_reason": capture.finish_reason,
        "gen_token_ids_sha256": prompt_ids_sha256([int(i) for i in capture.token_ids]),
        "states_sha256": _states_hash(capture),
    }


def _inp(prompt_id: str, ids: Sequence[int], sampling: dict[str, Any], n: int, pts: Any) -> Any:
    return {
        "prompt_id": prompt_id,
        "prompt_ids_sha256": prompt_ids_sha256(ids),
        "sampling": dict(sampling),
        "max_tokens": n,
        "points": list(pts),
    }


def _np32(array: Any) -> Any:
    """An MLX array as a float32 numpy array (the conversion the providers use)."""
    import mlx.core as mx
    import numpy as np

    return np.array(array.astype(mx.float32))


def _tokens(capture: Any) -> list[int]:
    return [int(i) for i in capture.token_ids]


# ---- T-U2-R-14 (material for AC-C2): the first run through the adapter --------------------------


def test_t_u2_r_00_load_and_provenance(real: Real) -> None:
    """A first capture of p01 (1 token): the adapter works end to end; records the provenance."""
    started = time.perf_counter()
    cap = real.capture("p01", ("final_norm",), 1, GREEDY)
    assert cap.dimension == 1024 and cap.n_gen == 1
    prov = cap.provenance
    table = {
        "revision": prov.revision is not None,
        "weights_sha256": prov.weights_sha256 is not None,
        "tokenizer_sha256": prov.tokenizer_sha256 is not None,
        "chat_template_sha256": prov.chat_template_sha256 is not None,
        "special_tokens_in": prov.special_tokens_in is not None,
        "eos_ids": prov.eos_ids is not None,
        "runtime.mlx": prov.runtime.get("mlx") is not None,
        "runtime.mlx_lm": prov.runtime.get("mlx_lm") is not None,
        "runtime.device": prov.runtime.get("device") is not None,
        "state_dtype": cap.state_dtype != "unknown",
    }
    source = "computed_or_default_cache"
    cache_dir = os.environ.get(ENV_HASH_CACHE)
    if cache_dir:
        key = re.sub(r"[^A-Za-z0-9._-]+", "_", str(real.snapshot.resolve()))
        files = sorted(real.snapshot.glob("*.safetensors"), key=lambda p: p.name)
        try:
            cached = json.loads((Path(cache_dir) / f"{key}.json").read_text(encoding="utf-8"))
            stamp = [[p.name, p.stat().st_size, p.stat().st_mtime_ns] for p in files]
            if cached.get("files") == stamp and cached.get("weights_sha256") == prov.weights_sha256:
                source = "cache_stamp_matched"
        except (OSError, ValueError):
            pass
    real.info["hash_source"] = source
    real.info["provenance"] = {
        "real_values": table,
        "state_dtype": cap.state_dtype,
        "tokenizer_sha256": prov.tokenizer_sha256,
        "chat_template_sha256": prov.chat_template_sha256,
        "runtime": dict(prov.runtime),
    }
    real.rec.add(
        "T-U2-R-14",
        "AC-C2 (material)",
        "provenance fields that are real values",
        input=_inp("p01", real.prompt_ids("p01"), GREEDY, 1, ["final_norm"]),
        output={"fields": table, "hash_source": source, "state_dtype": cap.state_dtype},
        compared_with="-",
        criterion="report",
        result="NUMBERS",
        started=started,
    )
    assert all(table.values()), table


# ---- T-U2-R-02 (AC-B1, B2 a): the generated tokens do not change -------------------------------


@pytest.mark.parametrize("prompt_id", PROMPT_IDS)
@pytest.mark.parametrize("name,sampling", [("greedy", GREEDY), ("seeded", SEEDED)])
def test_t_u2_r_02_tokens_equal_reference(
    real: Real, prompt_id: str, name: str, sampling: dict[str, Any]
) -> None:
    started = time.perf_counter()
    cap = real.capture(prompt_id, PILOT_POINTS, 64, sampling)
    expected, finish = real.reference(prompt_id, sampling, 64)
    same = _tokens(cap) == expected and cap.finish_reason == finish
    real.rec.add(
        "T-U2-R-02",
        "AC-B1/B2a",
        f"{prompt_id}/{name}",
        input=_inp(prompt_id, real.prompt_ids(prompt_id), sampling, 64, PILOT_POINTS),
        output={
            **_out(cap),
            "reference_gen_token_ids_sha256": prompt_ids_sha256(expected),
            "reference_finish_reason": finish,
        },
        compared_with="the model's own __call__ with cache and the same sampler",
        criterion="exact",
        result="PASS" if same else "FAIL",
        started=started,
    )
    assert same


# ---- T-U2-R-03 (AC-B1): the number of points does not change the tokens ------------------------


def test_t_u2_r_03_point_sets(real: Real) -> None:
    import numpy as np

    started = time.perf_counter()
    sets = {
        "one": ("final_norm",),
        "five": PILOT_POINTS,
        "all_block_out": (*(f"block_out:{i}" for i in range(24)), "final_norm"),
    }
    caps = {k: real.capture("p01", pts, 48, GREEDY) for k, pts in sets.items()}
    base = caps["one"]
    tokens_same = all(_tokens(c) == _tokens(base) for c in caps.values())
    shared_same = True
    pairs = [("one", "five"), ("one", "all_block_out"), ("five", "all_block_out")]
    for left, right in pairs:
        for name in set(caps[left].states) & set(caps[right].states):
            shared_same &= bool(np.array_equal(caps[left].states[name], caps[right].states[name]))
    real.rec.add(
        "T-U2-R-03",
        "AC-B1",
        "1 / 5 / 25 points",
        input=_inp("p01", real.prompt_ids("p01"), GREEDY, 48, ["one", "five", "all_block_out"]),
        output={k: _out(c) for k, c in caps.items()},
        compared_with="the same request with another set of points",
        criterion="exact (tokens) and bit (shared states)",
        result="PASS" if tokens_same and shared_same else "FAIL",
        started=started,
    )
    assert tokens_same and shared_same


# ---- the model's own forward pass over layers (mlp output tapped) -------------------------------


def _own_pass(real: Real, ids: Sequence[int], layers: Sequence[int]) -> dict[str, Any]:
    """One forward pass over ``ids`` with a fresh cache, spelled as the model's own loop: each
    layer is called as ``layer(h, mask, cache)`` (the model's DecoderLayer code). The mlp output of
    the wanted layers is read by wrapping ``layer.mlp`` in a module that records its result, and
    restored afterwards. Returns arrays for all positions: block_out:L, mlp_out:L, final_norm."""
    import mlx.core as mx
    import mlx.nn as nn
    from mlx_lm.models.base import create_attention_mask, create_ssm_mask

    model = real.provider._model
    tm = model.language_model.model

    class Tap(nn.Module):
        def __init__(self, inner: Any) -> None:
            super().__init__()
            self.inner = inner
            self.last: Any = None

        def __call__(self, x: Any) -> Any:
            self.last = self.inner(x)
            return self.last

    layer_list = list(tm.pipeline_layers)
    taps: dict[int, Tap] = {}
    originals: dict[int, Any] = {}
    out: dict[str, Any] = {}
    try:
        for index in layers:
            originals[index] = layer_list[index].mlp
            taps[index] = Tap(originals[index])
            layer_list[index].mlp = taps[index]
        cache = model.make_cache()
        h = tm.embed_tokens(mx.array(list(ids))[None])
        fa = create_attention_mask(h, cache[tm.fa_idx]) if tm.fa_idx is not None else None
        ssm = create_ssm_mask(h, cache[tm.ssm_idx]) if tm.ssm_idx is not None else None
        for index, (layer, c) in enumerate(zip(layer_list, cache, strict=True)):
            h = layer(h, mask=ssm if layer.is_linear else fa, cache=c)
            if index in taps:
                out[f"block_out:{index}"] = h
                out[f"mlp_out:{index}"] = taps[index].last
        out["final_norm"] = tm.norm(h)
        mx.eval(*out.values())
    finally:
        for index, original in originals.items():
            layer_list[index].mlp = original
    return out


# ---- T-U2-R-06 (AC-B2 b) ------------------------------------------------------------------------


@pytest.mark.parametrize("prompt_id", PROMPT_IDS)
def test_t_u2_r_06_equivalence(real: Real, prompt_id: str) -> None:
    from sensos_inference.providers.qwen35_mlx_capture import (
        PILOT_POSITIONS,
        Qwen35MLXEngine,
    )

    started = time.perf_counter()
    ids = real.prompt_ids(prompt_id)
    diff = Qwen35MLXEngine(real.provider._model, PILOT_POSITIONS).check_equivalence(ids)
    ok = diff == {"final_norm_max_abs_diff": 0.0, "logits_max_abs_diff": 0.0}
    real.rec.add(
        "T-U2-R-06",
        "AC-B2b",
        f"{prompt_id}/check_equivalence",
        input=_inp(prompt_id, ids, {}, 0, ["final_norm"]),
        output=diff,
        compared_with="the model's own forward (fresh caches, whole prompt)",
        criterion="bit",
        result="PASS" if ok else "FAIL",
        started=started,
    )
    assert ok, diff


@pytest.mark.parametrize("prompt_id", PROMPT_IDS)
def test_t_u2_r_06_tapped_points_against_own_layers(real: Real, prompt_id: str) -> None:
    """N-4: the values the engine taps (mlp_out, block_out) against the model's own layer loop."""
    import mlx.core as mx

    from sensos_inference.providers.qwen35_mlx_capture import (
        PILOT_POSITIONS,
        Qwen35MLXEngine,
    )

    started = time.perf_counter()
    ids = real.prompt_ids(prompt_id)
    try:
        engine = Qwen35MLXEngine(real.provider._model, PILOT_POSITIONS)
        engine._cache = real.provider._model.make_cache()
        _, taken = engine._run(mx.array(ids)[None], True)
        mx.eval(*taken.values())
        own = _own_pass(real, ids, (15, 19))
        diffs: dict[str, float] = {}
        for p in PILOT_POSITIONS:
            if p.kind == "final_norm":
                continue
            mine = taken[p.name]  # the last position, as the engine reads it
            theirs = own[f"{p.kind}:{p.layer}"][0, -1, :]
            diffs[f"{p.kind}:{p.layer}"] = float(
                mx.max(mx.abs(mine.astype(mx.float32) - theirs.astype(mx.float32)))
            )
    except Exception as exc:  # the comparison could not be made: N-4, recorded, not forced
        real.rec.not_verified.append(
            "tapped mlp_out/block_out against the model's own layers: not possible "
            f"({type(exc).__name__})"
        )
        real.rec.add(
            "T-U2-R-06",
            "AC-B2b",
            f"{prompt_id}/tapped points",
            input=_inp(prompt_id, ids, {}, 0, ["mlp_out:15", "block_out:15"]),
            output={"error": f"{type(exc).__name__}: {str(exc)[:160]}"},
            compared_with="the model's own layer loop with mlp output tapped",
            criterion="bit",
            result="NOT_RUN",
            started=started,
        )
        pytest.skip(f"N-4: the comparison could not be made ({type(exc).__name__}: {exc})")
    ok = all(v == 0.0 for v in diffs.values())
    real.rec.add(
        "T-U2-R-06",
        "AC-B2b",
        f"{prompt_id}/tapped points",
        input=_inp(prompt_id, ids, {}, 0, list(diffs)),
        output={"max_abs_diff": diffs},
        compared_with="the model's own layer loop with mlp output tapped",
        criterion="bit",
        result="PASS" if ok else "FAIL",
        started=started,
    )
    assert ok, diffs


# ---- T-U2-R-07, R-08 (AC-B3): numbers only ------------------------------------------------------


@pytest.mark.parametrize("prompt_id", ["p01", "p02", "p03"])
def test_t_u2_r_07_same_seed_twice(real: Real, prompt_id: str) -> None:
    import numpy as np

    started = time.perf_counter()
    a = real.capture(prompt_id, PILOT_POINTS, 64, SEEDED)
    b = real.capture(prompt_id, PILOT_POINTS, 64, SEEDED)
    same_tokens = _tokens(a) == _tokens(b)
    diffs = {
        n: float(np.max(np.abs(a.states[n] - b.states[n]))) if same_tokens else None
        for n in a.states
    }
    real.rec.add(
        "T-U2-R-07",
        "AC-B3",
        f"{prompt_id}/twice",
        input=_inp(prompt_id, real.prompt_ids(prompt_id), SEEDED, 64, PILOT_POINTS),
        output={"same_tokens": same_tokens, "first": _out(a), "second": _out(b)},
        compared_with="the same request again",
        criterion="report",
        result="NUMBERS",
        numbers={"max_abs_diff_per_point": diffs},
        started=started,
    )


@pytest.mark.parametrize("prompt_id", ["p01", "p02", "p03"])
def test_t_u2_r_08_sequential_against_full_pass(real: Real, prompt_id: str) -> None:
    import numpy as np

    started = time.perf_counter()
    cap = real.capture(prompt_id, ("final_norm",), 48, GREEDY)
    prompt = real.prompt_ids(prompt_id)
    full = _np32(_own_pass(real, [*prompt, *_tokens(cap)], ())["final_norm"][0])
    rows = cap.states["final_norm"]
    ref = full[cap.n_in - 1 : cap.n_in - 1 + cap.n_gen]
    cos = (rows * ref).sum(axis=1) / (np.linalg.norm(rows, axis=1) * np.linalg.norm(ref, axis=1))
    real.rec.add(
        "T-U2-R-08",
        "AC-B3",
        f"{prompt_id}/sequential vs full pass",
        input=_inp(prompt_id, prompt, GREEDY, 48, ["final_norm"]),
        output=_out(cap),
        compared_with="the model's own forward over prompt+generated tokens, same positions",
        criterion="report",
        result="NUMBERS",
        numbers={
            "max_abs_diff": float(np.abs(rows - ref).max()),
            "cosine_min": float(cos.min()),
            "cosine_mean": float(cos.mean()),
        },
        started=started,
    )


# ---- T-U2-R-09, 10, 11 (AC-C1): the row rule on the real model ----------------------------------

NO_THINK = {"enable_thinking": False}
ROW_CASES = [
    ("p01", 64, {}, "p01/64"),
    ("p02", 64, {}, "p02/64"),
    ("p03", 64, {}, "p03/64"),
    ("p04", 64, {}, "p04/64 (long prompt, prefill split)"),
    ("p01", 1, {}, "p01/max_tokens=1"),
    ("p01", 160, NO_THINK, "p01/no thinking (may reach EOS)"),
    ("p03", 160, NO_THINK, "p03/no thinking (may reach EOS)"),
]


@pytest.mark.parametrize("prompt_id,max_tokens,extra,label", ROW_CASES, ids=[c[3] for c in ROW_CASES])
def test_t_u2_r_09_10_11_rows(
    real: Real, prompt_id: str, max_tokens: int, extra: dict[str, Any], label: str
) -> None:
    import numpy as np

    started = time.perf_counter()
    sampling = {**GREEDY, **extra}
    cap = real.capture(prompt_id, ("final_norm",), max_tokens, sampling)
    prompt = real.prompt_ids(prompt_id, bool(sampling.get("enable_thinking", True)))
    assert len(prompt) == cap.n_in
    if prompt_id == "p04":
        assert cap.n_in > PREFILL_STEP, cap.n_in  # the prefill is split (R-11)
    n_in, n_gen = cap.n_in, cap.n_gen
    pos = np.arange(n_in - 1, n_in - 1 + n_gen, dtype=np.int64)
    eos = set(cap.provenance.eos_ids or ())
    exact = (
        bool(np.array_equal(cap.row_pos["final_norm"], pos))
        and bool(np.array_equal(cap.row_decides["final_norm"], np.arange(n_gen, dtype=np.int64)))
        and cap.states["final_norm"].shape[0] == n_gen == len(cap.token_ids)
        and not (eos & set(_tokens(cap)))
    )
    real.rec.add(
        "T-U2-R-11" if prompt_id == "p04" or max_tokens == 1 else "T-U2-R-09",
        "AC-C1(1)(3)",
        label,
        input=_inp(prompt_id, prompt, sampling, max_tokens, ["final_norm"]),
        output={**_out(cap), "reached_eos": cap.finish_reason == "eos"},
        compared_with="the row rule decides-next/1 computed from n_in and n_gen",
        criterion="exact",
        result="PASS" if exact else "FAIL",
        started=started,
    )
    assert exact
    if cap.finish_reason != "eos":
        real.rec.not_verified.append("EOS boundary not reached in some row cases (see reached_eos)")
    if n_gen < 2:
        return
    full = _np32(_own_pass(real, [*prompt, *_tokens(cap)], ())["final_norm"][0])
    rows = cap.states["final_norm"]
    unit_full = full / np.linalg.norm(full, axis=1, keepdims=True)
    unit_rows = rows / np.linalg.norm(rows, axis=1, keepdims=True)
    nearest = (unit_rows @ unit_full.T).argmax(axis=1)
    right = bool(np.array_equal(nearest, pos))
    real.rec.add(
        "T-U2-R-10",
        "AC-C1(2)",
        label,
        input=_inp(prompt_id, prompt, sampling, max_tokens, ["final_norm"]),
        output={"n_gen": n_gen, "rows_at_the_expected_nearest_position": int((nearest == pos).sum())},
        compared_with="positions of the model's own forward over prompt+generated tokens",
        criterion="nearest_position",
        result="PASS" if right else "FAIL",
        started=started,
    )
    assert right


# ---- T-U2-R-12, 13 (AC-C3) ----------------------------------------------------------------------


def _representable(arr: Any, dtype: str) -> bool:
    import numpy as np

    a = np.ascontiguousarray(arr, dtype="<f4")
    if dtype == "bfloat16":
        return bool(np.all((a.view("<u4") & 0xFFFF) == 0))
    if dtype == "float16":
        return bool(np.array_equal(a.astype("<f2").astype("<f4"), a))
    return dtype == "float32"


@pytest.mark.parametrize("prompt_id", ["p01", "p02", "p03"])
def test_t_u2_r_12_float32_is_exact(real: Real, prompt_id: str) -> None:
    import numpy as np

    started = time.perf_counter()
    cap = real.capture(prompt_id, PILOT_POINTS, 64, SEEDED)
    dtype = cap.state_dtype
    finite = all(bool(np.all(np.isfinite(a))) for a in cap.states.values())
    exact = {n: _representable(a, dtype) for n, a in cap.states.items()}
    ok = finite and all(exact.values())
    real.rec.add(
        "T-U2-R-12",
        "AC-C3",
        f"{prompt_id}/{dtype}",
        input=_inp(prompt_id, real.prompt_ids(prompt_id), SEEDED, 64, PILOT_POINTS),
        output={"state_dtype": dtype, "all_finite": finite, "representable_in_native_dtype": exact},
        compared_with="the values the native dtype can hold",
        criterion="bit",
        result="PASS" if ok else "FAIL",
        started=started,
    )
    assert ok, (dtype, finite, exact)


def test_t_u2_r_13_roundtrip_inside_mlx(real: Real) -> None:
    import mlx.core as mx

    from sensos_inference.providers.qwen35_mlx_capture import (
        PILOT_POSITIONS,
        Qwen35MLXEngine,
    )

    started = time.perf_counter()
    ids = real.prompt_ids("p01")
    engine = Qwen35MLXEngine(real.provider._model, PILOT_POSITIONS)
    engine._cache = real.provider._model.make_cache()
    h, taken = engine._run(mx.array(ids)[None], True)
    taken["final_norm"] = engine._tm.norm(h)[0, -1, :]
    mx.eval(*taken.values())
    result: dict[str, bool] = {}
    for name, value in taken.items():
        back = value.astype(mx.float32).astype(value.dtype)
        result[name] = bool(mx.array_equal(back, value))
    dtype = str(next(iter(taken.values())).dtype)
    ok = all(result.values())
    real.rec.add(
        "T-U2-R-13",
        "AC-C3",
        f"p01/{dtype}",
        input=_inp("p01", ids, {}, 0, list(taken)),
        output={"native_dtype": dtype, "roundtrip_equal": result},
        compared_with="the value in its native dtype",
        criterion="bit",
        result="PASS" if ok else "FAIL",
        started=started,
    )
    assert ok, result


# ---- T-U2-R-15 (AC-C4), R-16 (AC-A3, G2) --------------------------------------------------------


@pytest.mark.parametrize("point", ["block_out:24", "mlp_out:99", "embed:0", "block_out:-1"])
def test_t_u2_r_15_undeclared_points_are_refused(real: Real, point: str) -> None:
    from sensos_inference.observation import ObservationError

    started = time.perf_counter()
    calls: list[int] = []
    original = real.provider.capture_chat

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(*args, **kwargs)

    real.provider.capture_chat = counting
    try:
        with pytest.raises(ObservationError) as raised:
            real.capture("p01", (point,), 8, GREEDY)
    finally:
        real.provider.capture_chat = original
    codes = [i.code for i in raised.value.issues]
    ok = not calls and bool(codes)
    real.rec.add(
        "T-U2-R-15",
        "AC-C4",
        point,
        input={"point": point, "prompt_id": "p01"},
        output={"codes": codes, "provider_calls": len(calls)},
        compared_with="-",
        criterion="exact",
        result="PASS" if ok else "FAIL",
        started=started,
    )
    assert ok, (codes, calls)


def test_t_u2_r_16_arrays_are_read_only_and_a_second_capture_is_unchanged(real: Real) -> None:
    import numpy as np

    started = time.perf_counter()
    first = real.capture("p01", PILOT_POINTS, 32, GREEDY)
    kept = {n: a.copy() for n, a in first.states.items()}
    read_only = all(not a.flags.writeable for a in first.states.values())
    refused = True
    for arr in first.states.values():
        try:
            arr[0, 0] = 9e9
            refused = False
        except ValueError:
            pass
    untouched = all(np.array_equal(first.states[n], kept[n]) for n in kept)
    second = real.capture("p01", PILOT_POINTS, 32, GREEDY)
    same_again = _tokens(second) == _tokens(first) and all(
        np.array_equal(second.states[n], kept[n]) for n in kept
    )
    ok = read_only and refused and untouched and same_again
    real.rec.add(
        "T-U2-R-16",
        "AC-A3/G2",
        "p01/greedy",
        input=_inp("p01", real.prompt_ids("p01"), GREEDY, 32, PILOT_POINTS),
        output={
            "read_only": read_only,
            "assignment_refused": refused,
            "unchanged_after_write_attempt": untouched,
            "second_capture_equal": same_again,
        },
        compared_with="the first capture",
        criterion="exact",
        result="PASS" if ok else "FAIL",
        started=started,
    )
    assert ok
