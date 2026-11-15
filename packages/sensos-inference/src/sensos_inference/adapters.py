"""Observation Adapter (U2): turn a ``CaptureRequest`` into a call on an existing capture provider.

This module does not import ``mlx``, ``mlx-lm`` or ``transformers``. Providers are injected; the adapter
holds no model, engine or cache and exposes none.
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sensos_inference.observation import (
    ALIGNMENT_DECIDES_NEXT,
    UNKNOWN,
    CaptureCapabilities,
    CaptureRequest,
    ObservationCapture,
    ObservationError,
    ObservationIssue,
    ensure_valid,
    from_llama31,
    from_qwen35,
    llama31_mlx_capabilities,
    point_from_name,
    qwen35_mlx_capabilities,
    validate_capture,
    validate_request,
)

_PACKAGE = "sensos-inference"
_LLAMA_ADAPTER = "llama31-mlx-capture"
_QWEN_ADAPTER = "qwen35-mlx-capture"

_LLAMA_SAMPLING_KEYS = frozenset({"temperature", "top_k", "top_p", "seed"})
_QWEN_SAMPLING_KEYS = frozenset(
    {"temperature", "top_k", "top_p", "seed", "presence_penalty", "enable_thinking"}
)


@dataclass(frozen=True, slots=True)
class OriginUnknown:
    """A missing origin fact. Mirrors U4 ``Unknown2`` shape without importing nvs-kernel."""

    source: str
    reason: str = "unknown"

    def as_dict(self) -> dict[str, str]:
        return {"source": self.source, "reason": self.reason}


def _issue(code: str, path: str, message: str) -> ObservationIssue:
    return ObservationIssue(code, path, message)


def _sampling_kwargs(sampling: Mapping[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    if not isinstance(sampling, Mapping):
        raise ObservationError((_issue("OBS_REQ_SAMPLING", "sampling", "must be a mapping"),))
    unknown = sorted(str(key) for key in sampling if key not in allowed)
    if unknown:
        raise ObservationError(
            (
                _issue(
                    "OBS_REQ_SAMPLING",
                    "sampling",
                    f"unknown sampling key(s): {', '.join(unknown)}",
                ),
            )
        )
    return {str(key): sampling[key] for key in sampling}


def _package_version() -> str | OriginUnknown:
    try:
        return importlib.metadata.version(_PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        return OriginUnknown(source="origin.capture.version", reason="unavailable")


def _transformers_version() -> str | OriginUnknown:
    try:
        return importlib.metadata.version("transformers")
    except importlib.metadata.PackageNotFoundError:
        return OriginUnknown(source="origin.runtime.transformers", reason="unavailable")


def _hardware_string() -> str | OriginUnknown:
    """Best-effort host label. Never invents a value when sysctl is unavailable."""
    try:
        model = subprocess.check_output(["sysctl", "-n", "hw.model"], text=True, timeout=2).strip()
        chip = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True, timeout=2
        ).strip()
        mem_b = int(
            subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=2).strip()
        )
        gib = mem_b // (1024**3)
        if not model or not chip:
            return OriginUnknown(source="origin.hardware", reason="unavailable")
        return f"{model}/{chip}/{gib}GiB"
    except (OSError, subprocess.SubprocessError, ValueError):
        return OriginUnknown(source="origin.hardware", reason="unavailable")


def _str_or_unknown(value: object | None, source: str) -> str | OriginUnknown:
    if value is None:
        return OriginUnknown(source=source, reason="unknown")
    text = str(value)
    if not text:
        return OriginUnknown(source=source, reason="unknown")
    return text


def _quantization_from_snapshot(snapshot: Path | None) -> str | OriginUnknown:
    if snapshot is None or not snapshot.is_dir():
        return OriginUnknown(source="origin.quantization", reason="unavailable")
    config_path = snapshot / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return OriginUnknown(source="origin.quantization", reason="unavailable")
    quant = config.get("quantization")
    if quant is None:
        return "not_applicable"
    if isinstance(quant, Mapping):
        bits = quant.get("bits")
        group = quant.get("group_size")
        if type(bits) is int and type(group) is int:
            return f"{bits}bit/group{group}"
        return OriginUnknown(source="origin.quantization", reason="unavailable")
    return OriginUnknown(source="origin.quantization", reason="unavailable")


def _snapshot_dir(provider: Any) -> Path | None:
    raw = getattr(provider, "_snapshot_dir", None)
    if raw is None:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _origin_leaf(value: str | OriginUnknown) -> Any:
    return value.as_dict() if isinstance(value, OriginUnknown) else value


class ObservationAdapter(Protocol):
    def capabilities(self) -> CaptureCapabilities: ...

    def capture(
        self,
        messages: list[dict[str, str]],
        request: CaptureRequest,
        *,
        model_build_id: str,
        compute_environment: str,
    ) -> ObservationCapture: ...

    def origin_facts(self) -> dict[str, Any]: ...


class Llama31MLXAdapter:
    """Wraps a ``Llama31MLXCaptureProvider`` (or a duck-typed stand-in with ``capture_chat``)."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        # Observed only after a successful capture. Never guessed.
        self._observed_state_dtype: str | None = None
        self._last_capture: ObservationCapture | None = None

    def capabilities(self) -> CaptureCapabilities:
        """Capability declaration for callers.

        ``native_dtype`` is ``\"unknown\"`` until a successful ``capture`` has observed
        ``state_dtype``. Request and capture validation always use
        :meth:`_validation_capabilities` (pre-observation declaration) so a later update of
        this return value cannot rewrite what was checked.
        """
        native = self._observed_state_dtype if self._observed_state_dtype is not None else UNKNOWN
        return llama31_mlx_capabilities(native_dtype=native)

    def _validation_capabilities(self) -> CaptureCapabilities:
        """Declaration used with ``validate_request`` / ``validate_capture``: never pretends a dtype is known."""
        return llama31_mlx_capabilities(native_dtype=UNKNOWN)

    @property
    def observed_state_dtype(self) -> str | None:
        return self._observed_state_dtype

    @property
    def capabilities_phase(self) -> str:
        return "post_capture" if self._observed_state_dtype is not None else "pre_capture"

    def capture(
        self,
        messages: list[dict[str, str]],
        request: CaptureRequest,
        *,
        model_build_id: str,
        compute_environment: str,
    ) -> ObservationCapture:
        caps = self._validation_capabilities()
        ensure_valid(validate_request(request, caps))
        sampling = _sampling_kwargs(request.sampling, _LLAMA_SAMPLING_KEYS)
        # Llama declares only final_norm; undeclared points already failed validate_request.
        result = self._provider.capture_chat(messages, max_tokens=request.max_tokens, **sampling)
        capture = from_llama31(
            result, model_build_id=model_build_id, compute_environment=compute_environment
        )
        ensure_valid(validate_capture(capture, caps))
        if isinstance(capture.state_dtype, str) and capture.state_dtype != UNKNOWN:
            self._observed_state_dtype = capture.state_dtype
        self._last_capture = capture
        return capture

    def check_equivalence(
        self, prompt_ids: Sequence[int], token_ids: Sequence[int], **options: int
    ) -> dict[str, Any]:
        """The bit comparison of :func:`llama31_equivalence_check` on this adapter's provider."""
        # Lazy import of a sibling module: it is the one that imports MLX; this module never does.
        from sensos_inference.llama31_equivalence import llama31_equivalence_check

        return llama31_equivalence_check(self._provider, prompt_ids, token_ids, **options)

    def origin_facts(self) -> dict[str, Any]:
        model_ref = getattr(self._provider, "model_id", None)
        revision = getattr(self._provider, "revision", None)
        weights = mlx = mlx_lm = device = None
        stored = self._last_capture
        if stored is not None:
            model_ref = stored.provenance.model_ref
            revision = stored.provenance.revision
            weights = stored.provenance.weights_sha256
            runtime = stored.provenance.runtime
            mlx = runtime.get("mlx")
            mlx_lm = runtime.get("mlx_lm")
            device = runtime.get("device")

        version = _package_version()
        return {
            "origin": {
                "capture": {
                    "package": _PACKAGE,
                    "version": _origin_leaf(version),
                    "adapter": _LLAMA_ADAPTER,
                    "alignment": ALIGNMENT_DECIDES_NEXT,
                },
                "runtime": {
                    "backend": "mlx",
                    "mlx": _origin_leaf(_str_or_unknown(mlx, "origin.runtime.mlx")),
                    "mlx_lm": _origin_leaf(_str_or_unknown(mlx_lm, "origin.runtime.mlx_lm")),
                    "device": _origin_leaf(_str_or_unknown(device, "origin.runtime.device")),
                    "python": platform.python_version(),
                    "transformers": _origin_leaf(_transformers_version()),
                },
                "hardware": _origin_leaf(_hardware_string()),
                "quantization": _origin_leaf(_quantization_from_snapshot(_snapshot_dir(self._provider))),
                "model": _origin_leaf(_str_or_unknown(model_ref, "origin.model")),
                "revision": _origin_leaf(_str_or_unknown(revision, "origin.revision")),
                "weights_sha256": _origin_leaf(_str_or_unknown(weights, "origin.weights_sha256")),
            },
            "capabilities_phase": self.capabilities_phase,
            "observed_state_dtype": self._observed_state_dtype,
            # DC-U2-5 unresolved: version is package metadata only (no commit suffix).
            "version_policy": "package_metadata_only_pending_DC-U2-5",
        }


class Qwen35MLXAdapter:
    """Wraps a ``Qwen35MLXCaptureProvider`` (or a duck-typed stand-in with ``capture_chat``)."""

    def __init__(self, provider: Any, *, n_layers: int, dimension: int) -> None:
        if type(n_layers) is not int or n_layers < 1:
            raise ObservationError(
                (_issue("OBS_CAP_ARG", "n_layers", f"must be an int >= 1, got {n_layers!r}"),)
            )
        if type(dimension) is not int or dimension < 1:
            raise ObservationError(
                (_issue("OBS_CAP_ARG", "dimension", f"must be an int >= 1, got {dimension!r}"),)
            )
        self._provider = provider
        self._n_layers = n_layers
        self._dimension = dimension
        self._observed_state_dtype: str | None = None
        self._last_capture: ObservationCapture | None = None

    def capabilities(self) -> CaptureCapabilities:
        native = self._observed_state_dtype if self._observed_state_dtype is not None else UNKNOWN
        return qwen35_mlx_capabilities(
            n_layers=self._n_layers, dimension=self._dimension, native_dtype=native
        )

    def _validation_capabilities(self) -> CaptureCapabilities:
        return qwen35_mlx_capabilities(
            n_layers=self._n_layers, dimension=self._dimension, native_dtype=UNKNOWN
        )

    @property
    def observed_state_dtype(self) -> str | None:
        return self._observed_state_dtype

    @property
    def capabilities_phase(self) -> str:
        return "post_capture" if self._observed_state_dtype is not None else "pre_capture"

    def capture(
        self,
        messages: list[dict[str, str]],
        request: CaptureRequest,
        *,
        model_build_id: str,
        compute_environment: str,
    ) -> ObservationCapture:
        caps = self._validation_capabilities()
        ensure_valid(validate_request(request, caps))
        sampling = _sampling_kwargs(request.sampling, _QWEN_SAMPLING_KEYS)
        positions = _positions_from_request(request.points)
        result = self._provider.capture_chat(
            messages, positions=positions, max_tokens=request.max_tokens, **sampling
        )
        capture = from_qwen35(
            result, model_build_id=model_build_id, compute_environment=compute_environment
        )
        ensure_valid(validate_capture(capture, caps))
        if isinstance(capture.state_dtype, str) and capture.state_dtype != UNKNOWN:
            self._observed_state_dtype = capture.state_dtype
        self._last_capture = capture
        return capture

    def origin_facts(self) -> dict[str, Any]:
        model_ref = getattr(self._provider, "model_id", None)
        revision = getattr(self._provider, "revision", None)
        weights = mlx = mlx_lm = device = None
        stored = self._last_capture
        if stored is not None:
            model_ref = stored.provenance.model_ref
            revision = stored.provenance.revision
            weights = stored.provenance.weights_sha256
            runtime = stored.provenance.runtime
            mlx = runtime.get("mlx")
            mlx_lm = runtime.get("mlx_lm")
            device = runtime.get("device")
        version = _package_version()
        return {
            "origin": {
                "capture": {
                    "package": _PACKAGE,
                    "version": _origin_leaf(version),
                    "adapter": _QWEN_ADAPTER,
                    "alignment": ALIGNMENT_DECIDES_NEXT,
                },
                "runtime": {
                    "backend": "mlx",
                    "mlx": _origin_leaf(_str_or_unknown(mlx, "origin.runtime.mlx")),
                    "mlx_lm": _origin_leaf(_str_or_unknown(mlx_lm, "origin.runtime.mlx_lm")),
                    "device": _origin_leaf(_str_or_unknown(device, "origin.runtime.device")),
                    "python": platform.python_version(),
                    "transformers": _origin_leaf(_transformers_version()),
                },
                "hardware": _origin_leaf(_hardware_string()),
                "quantization": _origin_leaf(_quantization_from_snapshot(_snapshot_dir(self._provider))),
                "model": _origin_leaf(_str_or_unknown(model_ref, "origin.model")),
                "revision": _origin_leaf(_str_or_unknown(revision, "origin.revision")),
                "weights_sha256": _origin_leaf(_str_or_unknown(weights, "origin.weights_sha256")),
            },
            "capabilities_phase": self.capabilities_phase,
            "observed_state_dtype": self._observed_state_dtype,
            "version_policy": "package_metadata_only_pending_DC-U2-5",
        }


def _positions_from_request(points: Sequence[str]) -> list[Any]:
    """Map canonical point names to provider ``CapturePosition`` values, preserving request order."""
    # Lazy import: CapturePosition lives next to the provider; that module does not import MLX at
    # import time. Keeping the import local avoids a hard coupling for Llama-only use.
    from sensos_inference.providers.qwen35_mlx_capture import CapturePosition

    out: list[Any] = []
    for name in points:
        point = point_from_name(name)
        out.append(CapturePosition(point.kind, point.layer))
    return out


__all__ = [
    "Llama31MLXAdapter",
    "ObservationAdapter",
    "OriginUnknown",
    "Qwen35MLXAdapter",
]
