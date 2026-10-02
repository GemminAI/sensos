"""sensos doctor: environment checks, PASS/FAIL, no model loading.

Each check is independent, side-effect free, and never loads a model
(that is `smoke.py`'s job, not doctor's -- per design). GPU/backend
checks report an honest FAIL with a stated reason when a dependency or
backend is missing rather than skip the check or fabricate a PASS.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass

_SUPPORTED_ARCHITECTURES = {"x86_64", "aarch64", "arm64"}


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def check_os() -> CheckResult:
    system = platform.system()
    if system == "Linux":
        return CheckResult("OS", True, "Linux")
    return CheckResult("OS", False, f"{system} (this installer targets Linux)")


def check_architecture() -> CheckResult:
    machine = platform.machine()
    if machine in _SUPPORTED_ARCHITECTURES:
        return CheckResult("Architecture", True, machine)
    return CheckResult("Architecture", False, f"{machine} (unrecognized/untested)")


def check_python() -> CheckResult:
    version = sys.version_info
    detail = f"{version.major}.{version.minor}.{version.micro}"
    if (version.major, version.minor) >= (3, 12):
        return CheckResult("Python", True, detail)
    return CheckResult("Python", False, f"{detail} (requires >=3.12)")


def check_uv() -> CheckResult:
    path = shutil.which("uv")
    if path is None:
        return CheckResult("uv", False, "not found on PATH")
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CheckResult("uv", False, f"found at {path} but failed to run: {exc}")
    if result.returncode != 0:
        return CheckResult("uv", False, f"found at {path} but exited {result.returncode}")
    return CheckResult("uv", True, result.stdout.strip())


def check_sensos_runtime() -> CheckResult:
    try:
        import sensos

        return CheckResult("SensOS Runtime", True, f"sensos {sensos.__version__}")
    except ImportError as exc:
        return CheckResult("SensOS Runtime", False, str(exc))


def check_semantic_annotator() -> CheckResult:
    try:
        importlib.import_module("semantic_annotator")
        version = importlib.metadata.version("semantic-annotator")
    except ImportError as exc:
        return CheckResult("Semantic Annotator", False, str(exc))
    except importlib.metadata.PackageNotFoundError as exc:
        return CheckResult(
            "Semantic Annotator", False, f"importable but not installed as a package: {exc}"
        )
    return CheckResult("Semantic Annotator", True, f"semantic-annotator {version}")


def check_inference_backend() -> CheckResult:
    try:
        vllm = importlib.import_module("vllm")
    except ImportError as exc:
        return CheckResult(
            "Inference backend (vLLM)",
            False,
            f"vllm not installed ({exc}); run install.sh's vLLM step, or "
            "'uv pip install vllm'",
        )
    version = getattr(vllm, "__version__", "unknown version")
    return CheckResult("Inference backend (vLLM)", True, f"vllm {version}")


def check_gpu() -> CheckResult:
    try:
        torch = importlib.import_module("torch")
    except ImportError as exc:
        return CheckResult(
            "GPU/backend availability",
            False,
            f"torch not installed ({exc}); torch is installed as a vllm dependency",
        )
    try:
        available = torch.cuda.is_available()
    except Exception as exc:
        return CheckResult(
            "GPU/backend availability", False, f"torch.cuda.is_available() raised: {exc}"
        )
    if not available:
        return CheckResult(
            "GPU/backend availability",
            False,
            "torch.cuda.is_available() is False: no CUDA GPU detected",
        )
    count = torch.cuda.device_count()
    name = torch.cuda.get_device_name(0) if count else "unknown device"
    return CheckResult("GPU/backend availability", True, f"{count} CUDA device(s), e.g. {name}")


ALL_CHECKS = (
    check_os,
    check_architecture,
    check_python,
    check_uv,
    check_sensos_runtime,
    check_semantic_annotator,
    check_inference_backend,
    check_gpu,
)


def run_doctor() -> list[CheckResult]:
    return [check() for check in ALL_CHECKS]
