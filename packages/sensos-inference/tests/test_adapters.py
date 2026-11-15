"""U2 preparation tests (T-U2-P-*): Adapter logic with fake providers. No model, no MLX runtime."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from u2_support import (
    DEFAULT_NOT_VERIFIED,
    ENV_EVIDENCE,
    ENV_LLAMA,
    ENV_QWEN,
    FIXED_PROMPTS,
    build_evidence_record,
    maybe_write_evidence,
)

from sensos_inference.adapters import Llama31MLXAdapter, OriginUnknown, Qwen35MLXAdapter
from sensos_inference.observation import (
    UNKNOWN,
    CaptureRequest,
    ObservationError,
    from_llama31,
    llama31_mlx_capabilities,
    qwen35_mlx_capabilities,
)
from sensos_inference.providers.llama31_mlx_capture import ROW_RULE as LLAMA_ROW_RULE
from sensos_inference.providers.qwen35_mlx_capture import (
    ROW_RULE_TEXT as QWEN_ROW_RULE_TEXT,
)
from sensos_inference.providers.qwen35_mlx_capture import ROW_RULES as QWEN_ROW_RULES

MSG = [{"role": "user", "content": "hi"}]
PROMPT = [100, 5, 6, 101]
EOS = 39
DIM_L = 4096  # must match llama31_mlx_capabilities().dimension for validate_capture
DIM_Q = 6
LLAMA_BUILD = "llama31-mlx-4bit"
QWEN_BUILD = "qwen35-0.8b-bf16"
ADAPTERS_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "sensos_inference" / "adapters.py"
)


def _sha(ids: Any) -> str:
    return hashlib.sha256(np.asarray(list(ids), dtype="<i8").tobytes()).hexdigest()


def _llama_ok_result(*, tokens: list[int] | None = None, state_dtype: str = "bfloat16") -> SimpleNamespace:
    gen = [7, 8, 9] if tokens is None else list(tokens)
    n = len(gen)
    if n:
        states = np.zeros((n, DIM_L), dtype=np.float32)
        states[:, : min(8, DIM_L)] = np.arange(n * min(8, DIM_L), dtype=np.float32).reshape(n, min(8, DIM_L))
    else:
        states = np.zeros((0, DIM_L), dtype=np.float32)
    return SimpleNamespace(
        ok=True,
        text="x",
        model_ref="local/llama",
        revision="a" * 40,
        prompt_ids=list(PROMPT),
        token_ids=list(gen),
        states=states,
        state_dtype=None if n == 0 else state_dtype,
        finish_reason="eos",
        failure_kind=None,
        error=None,
        chat_template_sha256="c" * 64,
        tokenizer_sha256="d" * 64,
        special_tokens_in=[[0, 100]],
        weights_sha256="e" * 64,
        mlx_version="0.32.4",
        mlx_lm_version="0.32.2",
        device="Device(gpu, 0)",
        sampler={"temperature": 0.7, "top_k": 50, "top_p": 0.95, "seed": 0},
        max_tokens=64,
        row_rule=LLAMA_ROW_RULE,
    )


def _qwen_ok_result(
    *,
    tokens: list[int] | None = None,
    positions: list[dict[str, Any]] | None = None,
    state_dtype: str = "bfloat16",
) -> SimpleNamespace:
    gen = [7, 8, 9] if tokens is None else tokens
    n = len(gen)
    if positions is None:
        positions = [
            {"name": "L0.mlp_out", "kind": "mlp_out", "layer": 0, "row_rule": QWEN_ROW_RULES["mlp_out"]},
            {"name": "L0.block_out", "kind": "block_out", "layer": 0, "row_rule": QWEN_ROW_RULES["block_out"]},
            {"name": "final_norm", "kind": "final_norm", "layer": "final_norm", "row_rule": QWEN_ROW_RULES["final_norm"]},
        ]
    states = {
        p["name"]: (
            np.arange(n * DIM_Q, dtype=np.float32).reshape(n, DIM_Q)
            if n
            else np.zeros((0, DIM_Q), np.float32)
        )
        for p in positions
    }
    return SimpleNamespace(
        ok=True,
        text="x",
        model_ref="local/qwen",
        revision="b" * 40,
        hidden_size=DIM_Q,
        positions=positions,
        prompt_ids=list(PROMPT),
        token_ids=list(gen),
        states=states,
        state_dtype=state_dtype if n else None,
        finish_reason="eos",
        failure_kind=None,
        error=None,
        chat_template_sha256="c" * 64,
        chat_template_kwargs={"enable_thinking": True},
        tokenizer_sha256="d" * 64,
        special_tokens_in=[[0, 100]],
        prompt_ids_sha256=_sha(PROMPT),
        weights_sha256="f" * 64,
        eos_ids=[EOS],
        mlx_version="0.32.4",
        mlx_lm_version="0.32.2",
        device="Device(gpu, 0)",
        sampler={
            "temperature": 0.6,
            "top_k": 20,
            "top_p": 0.95,
            "seed": 0,
            "presence_penalty": 1.5,
        },
        max_tokens=64,
        row_rule=QWEN_ROW_RULE_TEXT,
    )


class FakeLlamaProvider:
    def __init__(self, result: Any | None = None, *, fail: Any | None = None) -> None:
        self.model_id = "local/llama"
        self.revision = "a" * 40
        self._snapshot_dir = None
        self.calls: list[tuple[Any, dict[str, Any]]] = []
        self._result = result
        self._fail = fail

    def capture_chat(self, messages: Any, **kwargs: Any) -> Any:
        self.calls.append((messages, dict(kwargs)))
        if self._fail is not None:
            return self._fail
        assert self._result is not None
        # Reflect actual sampling into provenance-like sampler when provided.
        sampler = dict(self._result.sampler)
        for key in ("temperature", "top_k", "top_p", "seed"):
            if key in kwargs:
                sampler[key] = kwargs[key]
        out = SimpleNamespace(**{**self._result.__dict__, "sampler": sampler, "max_tokens": kwargs.get("max_tokens", 64)})
        return out


class FakeQwenProvider:
    def __init__(self, result: Any | None = None, *, fail: Any | None = None) -> None:
        self.model_id = "local/qwen"
        self.revision = "b" * 40
        self._snapshot_dir = None
        self.calls: list[tuple[Any, dict[str, Any]]] = []
        self._result = result
        self._fail = fail

    def capture_chat(self, messages: Any, **kwargs: Any) -> Any:
        self.calls.append((messages, dict(kwargs)))
        if self._fail is not None:
            return self._fail
        assert self._result is not None
        positions = kwargs.get("positions")
        result = self._result
        if positions is not None:
            pos_dicts = [
                {
                    "name": p.name,
                    "kind": p.kind,
                    "layer": p.layer_label,
                    "row_rule": p.row_rule,
                }
                for p in positions
            ]
            n = len(result.token_ids)
            states = {
                p["name"]: (
                    np.arange(n * DIM_Q, dtype=np.float32).reshape(n, DIM_Q)
                    if n
                    else np.zeros((0, DIM_Q), np.float32)
                )
                for p in pos_dicts
            }
            sampler = dict(result.sampler)
            for key in ("temperature", "top_k", "top_p", "seed", "presence_penalty"):
                if key in kwargs:
                    sampler[key] = kwargs[key]
            result = SimpleNamespace(
                **{
                    **result.__dict__,
                    "positions": pos_dicts,
                    "states": states,
                    "sampler": sampler,
                    "max_tokens": kwargs.get("max_tokens", 64),
                    "chat_template_kwargs": {
                        "enable_thinking": kwargs.get(
                            "enable_thinking", result.chat_template_kwargs.get("enable_thinking", True)
                        )
                    },
                }
            )
        return result


def _codes(exc: ObservationError) -> list[str]:
    return [i.code for i in exc.issues]


# ---- T-U2-P-01..11 ------------------------------------------------------------------------------
# T-U2-P-12 lives in test_u2_p12_u1_observation_opt_in.py (explicit opt-in; can load mlx.core).


def test_t_u2_p_01_undeclared_point_rejects_before_provider() -> None:
    provider = FakeLlamaProvider(result=_llama_ok_result())
    adapter = Llama31MLXAdapter(provider)
    request = CaptureRequest(points=("block_out:0",), max_tokens=8)
    with pytest.raises(ObservationError) as info:
        adapter.capture(MSG, request, model_build_id=LLAMA_BUILD, compute_environment="mlx-4bit")
    assert "OBS_REQ_POINT_UNDECLARED" in _codes(info.value)
    assert provider.calls == []


def test_t_u2_p_02_qwen_point_order_preserved() -> None:
    provider = FakeQwenProvider(result=_qwen_ok_result())
    adapter = Qwen35MLXAdapter(provider, n_layers=2, dimension=DIM_Q)
    points = ("final_norm", "mlp_out:0", "block_out:0")
    request = CaptureRequest(points=points, max_tokens=8)
    capture = adapter.capture(MSG, request, model_build_id=QWEN_BUILD, compute_environment="mlx-bf16")
    assert len(provider.calls) == 1
    passed = provider.calls[0][1]["positions"]
    assert [p.name for p in passed] == ["final_norm", "L0.mlp_out", "L0.block_out"]
    assert capture.points == points


def test_t_u2_p_03_unknown_sampling_key() -> None:
    provider = FakeLlamaProvider(result=_llama_ok_result())
    adapter = Llama31MLXAdapter(provider)
    request = CaptureRequest(points=("final_norm",), max_tokens=8, sampling={"temperature": 0.1, "foo": 1})
    with pytest.raises(ObservationError) as info:
        adapter.capture(MSG, request, model_build_id=LLAMA_BUILD, compute_environment="mlx-4bit")
    assert _codes(info.value) == ["OBS_REQ_SAMPLING"]
    assert provider.calls == []


def test_t_u2_p_04_sampling_defaults_and_partial() -> None:
    provider = FakeLlamaProvider(result=_llama_ok_result())
    adapter = Llama31MLXAdapter(provider)
    request = CaptureRequest(points=("final_norm",), max_tokens=8, sampling={"seed": 11})
    capture = adapter.capture(MSG, request, model_build_id=LLAMA_BUILD, compute_environment="mlx-4bit")
    assert provider.calls[0][1]["seed"] == 11
    assert "temperature" not in provider.calls[0][1]
    assert capture.provenance.sampler["seed"] == 11


def test_t_u2_p_05_provider_failure_becomes_obs_src_failed() -> None:
    fail = SimpleNamespace(
        ok=False,
        text="",
        model_ref="local/llama",
        revision=None,
        prompt_ids=[],
        token_ids=[],
        states=np.zeros((0, DIM_L), np.float32),
        state_dtype=None,
        finish_reason=None,
        failure_kind="load_failed",
        error="boom",
        chat_template_sha256=None,
        tokenizer_sha256=None,
        special_tokens_in=None,
        weights_sha256=None,
        mlx_version=None,
        mlx_lm_version=None,
        device=None,
        sampler={},
        max_tokens=8,
        row_rule=LLAMA_ROW_RULE,
    )
    provider = FakeLlamaProvider(fail=fail)
    adapter = Llama31MLXAdapter(provider)
    request = CaptureRequest(points=("final_norm",), max_tokens=8)
    with pytest.raises(ObservationError) as info:
        adapter.capture(MSG, request, model_build_id=LLAMA_BUILD, compute_environment="mlx-4bit")
    assert "OBS_SRC_FAILED" in _codes(info.value)


def test_t_u2_p_06_immediate_eos_t0() -> None:
    provider = FakeLlamaProvider(result=_llama_ok_result(tokens=[]))
    adapter = Llama31MLXAdapter(provider)
    request = CaptureRequest(points=("final_norm",), max_tokens=8)
    capture = adapter.capture(MSG, request, model_build_id=LLAMA_BUILD, compute_environment="mlx-4bit")
    assert capture.n_rows == 0
    assert capture.n_gen == 0
    assert capture.finish_reason == "eos"


def test_t_u2_p_07_capabilities_before_and_after() -> None:
    provider = FakeLlamaProvider(result=_llama_ok_result(state_dtype="bfloat16"))
    adapter = Llama31MLXAdapter(provider)
    before = adapter.capabilities()
    assert before.native_dtype == UNKNOWN
    assert adapter.capabilities_phase == "pre_capture"
    request = CaptureRequest(points=("final_norm",), max_tokens=8)
    # Request checked against the pre-observation declaration (unknown native_dtype).
    ensure_caps = adapter._validation_capabilities()
    assert ensure_caps.native_dtype == UNKNOWN
    capture = adapter.capture(MSG, request, model_build_id=LLAMA_BUILD, compute_environment="mlx-4bit")
    after = adapter.capabilities()
    assert after.native_dtype == "bfloat16"
    assert adapter.capabilities_phase == "post_capture"
    assert capture.state_dtype == "bfloat16"
    # A request validated with the pre-capture declaration still matches the fixed point set.
    assert before.points == after.points == ("final_norm",)


def test_t_u2_p_08_origin_facts() -> None:
    provider = FakeLlamaProvider(result=_llama_ok_result())
    adapter = Llama31MLXAdapter(provider)
    before = adapter.origin_facts()
    assert before["origin"]["capture"]["package"] == "sensos-inference"
    assert before["origin"]["capture"]["adapter"] == "llama31-mlx-capture"
    assert before["origin"]["capture"]["alignment"] == "decides-next/1"
    assert before["origin"]["runtime"]["backend"] == "mlx"
    assert before["origin"]["runtime"]["python"]
    # No capture yet: model/runtime hashes are missing markers, not guesses.
    assert isinstance(before["origin"]["runtime"]["mlx"], dict)
    assert before["origin"]["runtime"]["mlx"]["source"] == "origin.runtime.mlx"
    adapter.capture(
        MSG,
        CaptureRequest(points=("final_norm",), max_tokens=8),
        model_build_id=LLAMA_BUILD,
        compute_environment="mlx-4bit",
    )
    after = adapter.origin_facts()
    assert after["origin"]["model"] == "local/llama"
    assert after["origin"]["revision"] == "a" * 40
    assert after["origin"]["weights_sha256"] == "e" * 64
    assert after["origin"]["runtime"]["mlx"] == "0.32.4"
    assert after["version_policy"] == "package_metadata_only_pending_DC-U2-5"
    assert isinstance(after["origin"]["capture"]["version"], (str, dict))


def test_t_u2_p_09_adapters_module_import_policy() -> None:
    tree = ast.parse(ADAPTERS_PATH.read_text(encoding="utf-8"))
    forbidden = {"mlx", "mlx_lm", "transformers"}
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in forbidden or alias.name.replace("-", "_") in {"mlx_lm"}:
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in forbidden or node.module.replace("-", "_").startswith("mlx_lm"):
                found.add(node.module)
    assert found == set()
    # No public getters for model / engine / cache.
    source = ADAPTERS_PATH.read_text(encoding="utf-8")
    for name in ("def model(", "def engine(", "def cache(", "def get_model", "def get_engine"):
        assert name not in source


def test_t_u2_p_10_evidence_record_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="not_verified"):
        build_evidence_record(
            run_id="r1",
            adapter="llama31-mlx-capture",
            code={"repository": "sensos", "branch": "x", "commit": "a" * 40, "dirty": False, "adapter": "llama31-mlx-capture"},
            environment={"python": "3.12.13"},
            model={"snapshot": "Meta-Llama"},
            checks=[],
            not_verified=(),
            host="Mac15,6/Apple M3 Pro/18GiB",
        )
    record = build_evidence_record(
        run_id="r1",
        adapter="llama31-mlx-capture",
        code={"repository": "sensos", "branch": "x", "commit": "a" * 40, "dirty": False, "adapter": "llama31-mlx-capture"},
        environment={"python": "3.12.13", "mlx": "0.32.4", "mlx_lm": "0.32.2", "transformers": "5.22.2", "numpy": "2.5.4"},
        model={
            "model_ref": "local/llama",
            "snapshot": "Meta-Llama-3.1-8B-Instruct-4bit",
            "revision": "a" * 40,
            "weights_sha256": "b" * 64,
            "hash_source": "cache",
            "state_dtype": "bfloat16",
        },
        checks=[
            {
                "id": "T-U2-R-01",
                "ac": "AC-B1",
                "case": "p01/greedy",
                "input": {"prompt_ids_sha256": "c" * 64, "sampling": {"top_k": 1}, "max_tokens": 64, "points": ["final_norm"]},
                "output": {"n_in": 4, "n_gen": 1, "finish_reason": "eos", "gen_token_ids_sha256": "d" * 64},
                "compared_with": "Llama31MLXProvider.generate_chat",
                "criterion": "exact",
                "result": "PASS",
                "numbers": {},
            }
        ],
        not_verified=DEFAULT_NOT_VERIFIED,
        host="Mac15,6/Apple M3 Pro/18GiB",
        os_name="macOS 26.6.2",
    )
    assert record["evidence_kind"] == "real_machine"
    assert record["not_verified"]
    text = json.dumps(record)
    assert "Users/" not in text
    assert '"token_ids"' not in text
    assert '"prompt_ids"' not in text
    assert '"states"' not in text
    assert FIXED_PROMPTS["p01"][0]["content"] not in text

    monkeypatch.delenv(ENV_EVIDENCE, raising=False)
    assert maybe_write_evidence(record) is None
    monkeypatch.setenv(ENV_EVIDENCE, str(tmp_path))
    path = maybe_write_evidence(record)
    assert path is not None and path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["record_version"] == "u2-evidence/1"


def test_t_u2_p_11_real_machine_tests_skip_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_LLAMA, raising=False)
    monkeypatch.delenv(ENV_QWEN, raising=False)
    import u2_support as support

    assert support.llama_real_machine_available() is False
    assert support.qwen_real_machine_available() is False
    # Nested pytest.main can disturb the outer session; use a subprocess instead.
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k not in (ENV_LLAMA, ENV_QWEN)}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(Path(__file__).with_name("test_u2_real_machine.py")),
            "-k",
            "t_u2_r_",
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "skipped" in (proc.stdout + proc.stderr).lower() or "2 skipped" in proc.stdout


def test_origin_unknown_roundtrip() -> None:
    missing = OriginUnknown(source="origin.runtime.mlx", reason="unavailable")
    assert missing.as_dict() == {"source": "origin.runtime.mlx", "reason": "unavailable"}


def test_from_llama31_still_works_on_fake_result() -> None:
    # Sanity: fake result shape matches U1 conversion (Adapter depends on this).
    capture = from_llama31(_llama_ok_result(), model_build_id=LLAMA_BUILD, compute_environment="mlx-4bit")
    assert capture.points == ("final_norm",)
    assert llama31_mlx_capabilities().equivalence_check == "none"
    assert qwen35_mlx_capabilities(n_layers=2, dimension=6).equivalence_check == "bit"
