from __future__ import annotations

import subprocess
import sys
import types
from collections import namedtuple
from typing import Any

import pytest

from sensos.doctor import (
    ALL_CHECKS,
    check_architecture,
    check_gpu,
    check_inference_backend,
    check_os,
    check_python,
    check_semantic_annotator,
    check_sensos_runtime,
    check_uv,
    run_doctor,
)

# -- OS / architecture --------------------------------------------------


def test_check_os_passes_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    result = check_os()
    assert result.passed is True
    assert result.detail == "Linux"


def test_check_os_fails_on_non_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    result = check_os()
    assert result.passed is False
    assert "Darwin" in result.detail


def test_check_architecture_passes_for_known_arch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    result = check_architecture()
    assert result.passed is True
    assert result.detail == "x86_64"


def test_check_architecture_fails_for_unknown_arch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.machine", lambda: "riscv64")
    result = check_architecture()
    assert result.passed is False


# -- Python ---------------------------------------------------------------


_FakeVersionInfo = namedtuple(
    "_FakeVersionInfo", ["major", "minor", "micro", "releaselevel", "serial"]
)


def test_check_python_passes_for_3_12(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_version = _FakeVersionInfo(3, 12, 5, "final", 0)
    monkeypatch.setattr(sys, "version_info", fake_version)
    result = check_python()
    assert result.passed is True
    assert result.detail == "3.12.5"


def test_check_python_fails_below_3_12(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_version = _FakeVersionInfo(3, 11, 9, "final", 0)
    monkeypatch.setattr(sys, "version_info", fake_version)
    result = check_python()
    assert result.passed is False
    assert "3.11.9" in result.detail


# -- uv ---------------------------------------------------------------------


def test_check_uv_fails_when_not_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    result = check_uv()
    assert result.passed is False
    assert "not found" in result.detail


def test_check_uv_passes_when_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/uv")

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="uv 0.11.29\n")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = check_uv()
    assert result.passed is True
    assert result.detail == "uv 0.11.29"


def test_check_uv_fails_when_command_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/uv")

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = check_uv()
    assert result.passed is False


# -- SensOS Runtime / Semantic Annotator -------------------------------------


def test_check_sensos_runtime_passes() -> None:
    result = check_sensos_runtime()
    assert result.passed is True
    assert "sensos" in result.detail


def test_check_semantic_annotator_passes() -> None:
    result = check_semantic_annotator()
    assert result.passed is True
    assert "semantic-annotator" in result.detail


def test_check_semantic_annotator_fails_when_not_importable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import_module(name: str) -> None:
        raise ImportError(f"No module named {name!r}")

    monkeypatch.setattr("importlib.import_module", fake_import_module)
    result = check_semantic_annotator()
    assert result.passed is False


# -- Inference backend (vLLM) -------------------------------------------------


def test_check_inference_backend_fails_when_vllm_not_installed() -> None:
    # vllm is genuinely not installed in this test environment.
    result = check_inference_backend()
    assert result.passed is False
    assert "vllm not installed" in result.detail


def test_check_inference_backend_passes_when_vllm_installed(fake_module_factory: Any) -> None:
    fake_module_factory("vllm", __version__="0.25.1")
    result = check_inference_backend()
    assert result.passed is True
    assert result.detail == "vllm 0.25.1"


# -- GPU ----------------------------------------------------------------------


def test_check_gpu_fails_when_torch_not_installed() -> None:
    result = check_gpu()
    assert result.passed is False
    assert "torch not installed" in result.detail


def test_check_gpu_fails_when_cuda_unavailable(fake_module_factory: Any) -> None:
    class _FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = _FakeCuda()  # type: ignore[attr-defined]
    import sys as _sys

    _sys.modules["torch"] = fake_torch
    try:
        result = check_gpu()
    finally:
        del _sys.modules["torch"]
    assert result.passed is False
    assert "no CUDA GPU detected" in result.detail


def test_check_gpu_passes_when_cuda_available() -> None:
    class _FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def device_count() -> int:
            return 1

        @staticmethod
        def get_device_name(index: int) -> str:
            return "NVIDIA L4"

    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = _FakeCuda()  # type: ignore[attr-defined]
    sys.modules["torch"] = fake_torch
    try:
        result = check_gpu()
    finally:
        del sys.modules["torch"]
    assert result.passed is True
    assert "NVIDIA L4" in result.detail


# -- run_doctor aggregate ------------------------------------------------------


def test_run_doctor_runs_every_check() -> None:
    results = run_doctor()
    assert len(results) == len(ALL_CHECKS)
    assert [r.name for r in results] == [
        "OS",
        "Architecture",
        "Python",
        "uv",
        "SensOS Runtime",
        "Semantic Annotator",
        "Inference backend (vLLM)",
        "GPU/backend availability",
    ]
