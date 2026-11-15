"""Observation Interface (U1): types, checks and conversions for internal-state capture.

This module only describes and checks values. It takes no model, engine, cache or hook, and it holds no
write operation: every function takes values and returns new values (or issues). It imports numpy and
the standard library only; results of the existing capture providers are read by attribute (duck
typing), so neither MLX nor ``sensos_inference.providers`` is imported.

Row rule (the same in both MLX capture loops): row ``i`` is the state at the position of the token that
was *fed* in the step that decided ``token_ids[i]``. With ``sequence = prompt_ids ++ token_ids``::

    T = n_gen,  row_pos[i] = n_in - 1 + i,  row_decides[i] = i

The step that decides EOS gives no row and no token id, so EOS ending and length-limit ending have the
same shapes; only ``finish_reason`` tells them apart.

Nothing here computes a ``space_id`` hash: ``space_materials`` returns the six materials only.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

import numpy as np

# ---- constants ---------------------------------------------------------------------------------

#: Kinds U1 accepts: the ones the existing providers can capture.
KINDS = ("block_out", "mlp_out", "final_norm")
#: Kinds named by the interface vocabulary that have no capture implementation yet; always rejected.
RESERVED_KINDS = ("embed", "mlp_act", "attn_out", "attn_summary", "logit_summary")
#: Row range of a capture: only the steps that decided a generated token.
TOKEN_SCOPES = ("gen",)
DELIVERIES = ("per-request", "per-token")
EQUIVALENCE_CHECKS = ("bit", "numeric", "none")
#: How a capture can end. A provider result with ``finish_reason=None`` (``max_tokens=0``) is not converted.
FINISH_REASONS = ("eos", "length")
#: A value that is not known. Never filled in by guessing.
UNKNOWN = "unknown"
#: Name of the row/token alignment of ``row_positions``.
ALIGNMENT_DECIDES_NEXT = "decides-next/1"
#: Name of the hidden-trajectory space rule (the materials of ``space_materials`` follow it).
SPACE_RULE = "nvs.hidden-trajectory.space/1"

_MAX_DIMENSION = 2**53 - 1

_LLAMA_ADAPTER = "llama31-mlx-capture"
_QWEN_ADAPTER = "qwen35-mlx-capture"
_LLAMA_FINAL_NORM = "llama31-mlx-final-norm/1"
_QWEN_ROW_RULE = {
    "mlp_out": "qwen35-mlx-mlp-out/1",
    "block_out": "qwen35-mlx-block-out/1",
    "final_norm": "qwen35-mlx-final-norm/1",
}
_LLAMA_HIDDEN_DIMENSION = 4096
_FAILED_KINDS = ("load_failed", "generate_failed", "eos_missing")

# Same text as the providers' own row-rule descriptions (``llama31_mlx_capture.ROW_RULE``,
# ``qwen35_mlx_capture.ROW_RULE_TEXT``); a converted result must carry exactly this text.
_LLAMA_SOURCE_TEXT = (
    "row i = last-position output of model.model (after the final RMSNorm) in the step that decided "
    "token_ids[i]; row 0 is the state at the last prompt position; the step that decides EOS gives no "
    "row and no token id; the last token id has no row"
)
_QWEN_SOURCE_TEXT = (
    "row i = last-position value at the capture position in the step that decided token_ids[i]; "
    "row 0 is the state at the last prompt position; the step that decides EOS gives no row and no "
    "token id; the last token id has no row"
)

_TEXT = re.compile(r"[A-Za-z0-9._:/+@=-]{1,256}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ROW_RULE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*-(block-out|mlp-out|final-norm)/[1-9][0-9]*")
_POINT_NAME = re.compile(r"(final_norm|(block_out|mlp_out):(0|[1-9][0-9]*))")
_LEGACY_POINT_NAME = re.compile(r"(final_norm|L(0|[1-9][0-9]*)\.(block_out|mlp_out))")

# ---- issues and errors -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ObservationIssue:
    """One problem found by a check. ``path`` is the field path, e.g. ``states.block_out:16``."""

    code: str
    path: str
    message: str


class ObservationError(ValueError):
    """Raised when there is at least one issue (``ensure_valid``, constructors, conversions)."""

    def __init__(self, issues: Sequence[ObservationIssue]) -> None:
        self.issues = tuple(issues)
        if self.issues:
            first = self.issues[0]
            text = f"{first.code} at {first.path}: {first.message} ({len(self.issues)} issue(s))"
        else:
            text = "observation error (no issues)"
        super().__init__(text)


def _issue(code: str, path: str, message: str) -> ObservationIssue:
    return ObservationIssue(code, path, message)


# ---- observation points ------------------------------------------------------------------------


def _name_issue(name: object, path: str) -> ObservationIssue:
    """The issue for a string that is not a canonical point name."""
    head = name.split(":", 1)[0] if isinstance(name, str) else None
    if head in RESERVED_KINDS:
        return _issue("OBS_POINT_KIND_RESERVED", path, f"kind {head!r} is reserved and not capturable")
    return _issue("OBS_POINT_NAME", path, f"not a canonical point name: {name!r}")


@dataclass(frozen=True, slots=True)
class ObservationPoint:
    """Where in the network a state is read. ``layer`` is the 0-based decoder-layer index for
    ``block_out`` / ``mlp_out`` and ``None`` for ``final_norm``. Checked on construction."""

    kind: str
    layer: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in KINDS:
            reserved = isinstance(self.kind, str) and self.kind in RESERVED_KINDS
            code = "OBS_POINT_KIND_RESERVED" if reserved else "OBS_POINT_KIND"
            raise ObservationError((_issue(code, "kind", f"kind must be one of {KINDS}, got {self.kind!r}"),))
        if self.kind == "final_norm":
            if self.layer is not None:
                raise ObservationError((_issue("OBS_POINT_LAYER", "layer", "final_norm has no layer index"),))
        elif type(self.layer) is not int or self.layer < 0:
            message = f"{self.kind} needs an int layer >= 0, got {self.layer!r}"
            raise ObservationError((_issue("OBS_POINT_LAYER", "layer", message),))

    @property
    def name(self) -> str:
        """Canonical point name: ``final_norm`` or ``<kind>:<layer>``."""
        return "final_norm" if self.kind == "final_norm" else f"{self.kind}:{self.layer}"

    @property
    def legacy_name(self) -> str:
        """The name the existing capture code uses (``CapturePosition.name``): ``L<layer>.<kind>``."""
        return "final_norm" if self.kind == "final_norm" else f"L{self.layer}.{self.kind}"

    @property
    def layer_label(self) -> int | str:
        """The ``layer`` material of the space rule: an int, or the string ``final_norm``."""
        return "final_norm" if self.layer is None else int(self.layer)

    @property
    def kind_slug(self) -> str:
        return self.kind.replace("_", "-")


def point_from_name(name: str) -> ObservationPoint:
    """Read a canonical point name (``block_out:16``, ``final_norm``) and nothing else."""
    match = _POINT_NAME.fullmatch(name) if isinstance(name, str) else None
    if match is None:
        raise ObservationError((_name_issue(name, "name"),))
    if match.group(1) == "final_norm":
        return ObservationPoint("final_norm")
    return ObservationPoint(match.group(2), int(match.group(3)))


def point_from_legacy_name(name: str) -> ObservationPoint:
    """Read an existing-code name (``L15.mlp_out``, ``final_norm``) and nothing else."""
    match = _LEGACY_POINT_NAME.fullmatch(name) if isinstance(name, str) else None
    if match is None:
        raise ObservationError((_issue("OBS_POINT_NAME", "name", f"not a legacy point name: {name!r}"),))
    if match.group(1) == "final_norm":
        return ObservationPoint("final_norm")
    return ObservationPoint(match.group(3), int(match.group(2)))


def _parse_point(name: object) -> ObservationPoint | None:
    return point_from_name(name) if isinstance(name, str) and _POINT_NAME.fullmatch(name) else None  # type: ignore[arg-type]


# ---- rows --------------------------------------------------------------------------------------


def row_positions(n_in: int, n_gen: int) -> tuple[np.ndarray, np.ndarray]:
    """``(row_pos, row_decides)`` for ``n_in`` prompt tokens and ``n_gen`` generated tokens.

    Both are read-only int64 arrays of length ``n_gen``: ``row_pos = arange(n_in - 1, n_in - 1 + n_gen)``
    and ``row_decides = arange(n_gen)``.
    """
    if type(n_in) is not int or type(n_gen) is not int or n_in < 1 or n_gen < 0:
        raise ObservationError(
            (_issue("OBS_ROW_ARG", "n_in,n_gen", f"need int n_in >= 1 and int n_gen >= 0, got {n_in!r}, {n_gen!r}"),)
        )
    row_pos = np.arange(n_in - 1, n_in - 1 + n_gen, dtype=np.int64)
    row_decides = np.arange(n_gen, dtype=np.int64)
    row_pos.setflags(write=False)
    row_decides.setflags(write=False)
    return row_pos, row_decides


# ---- row-rule registry -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RowRuleSpec:
    """One registered ``row_rule``. ``source_text`` is the provider's own description of the rule."""

    name: str
    kind: str
    adapter: str
    alignment: str
    source_text: str


#: The registry of row rules. Only captures that exist are registered (no HF / vLLM rule yet).
#: A rule name carries its kind: ``<model family>-<runtime>-<kind slug>/<version>``.
ROW_RULES: Mapping[str, RowRuleSpec] = MappingProxyType(
    {
        spec.name: spec
        for spec in (
            RowRuleSpec(_LLAMA_FINAL_NORM, "final_norm", _LLAMA_ADAPTER, ALIGNMENT_DECIDES_NEXT, _LLAMA_SOURCE_TEXT),
            RowRuleSpec(
                _QWEN_ROW_RULE["mlp_out"], "mlp_out", _QWEN_ADAPTER, ALIGNMENT_DECIDES_NEXT, _QWEN_SOURCE_TEXT
            ),
            RowRuleSpec(
                _QWEN_ROW_RULE["block_out"], "block_out", _QWEN_ADAPTER, ALIGNMENT_DECIDES_NEXT, _QWEN_SOURCE_TEXT
            ),
            RowRuleSpec(
                _QWEN_ROW_RULE["final_norm"], "final_norm", _QWEN_ADAPTER, ALIGNMENT_DECIDES_NEXT, _QWEN_SOURCE_TEXT
            ),
        )
    }
)

# ---- data types --------------------------------------------------------------------------------


def _empty_mapping() -> Mapping[str, Any]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureCapabilities:
    """What an adapter says it can capture. Not checked on construction: use ``validate_capabilities``."""

    adapter: str
    runtime: str
    dimension: int
    points: tuple[str, ...]
    row_rule: Mapping[str, str]
    final_norm_applied: Mapping[str, bool | str]
    token_scope: tuple[str, ...] = TOKEN_SCOPES
    delivery: str
    native_dtype: str
    equivalence_check: str
    unknowns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureRequest:
    """What a caller wants captured. Not checked on construction: use ``validate_request``."""

    points: tuple[str, ...]
    max_tokens: int
    token_scope: str = "gen"
    sampling: Mapping[str, Any] = field(default_factory=_empty_mapping)
    logit_summary: None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureProvenance:
    """Where a capture came from. A value that is not known is ``None`` and is listed in ``unknowns``."""

    model_ref: str
    revision: str | None
    weights_sha256: str | None
    tokenizer_sha256: str | None
    chat_template_sha256: str | None
    special_tokens_in: tuple[tuple[int, int], ...] | None
    prompt_ids_sha256: str
    gen_token_ids_sha256: str
    runtime: Mapping[str, str | None]
    sampler: Mapping[str, Any]
    max_tokens: int
    chat_template_kwargs: Mapping[str, Any] = field(default_factory=_empty_mapping)
    eos_ids: tuple[int, ...] | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationCapture:
    """The result of one captured generation. Not checked on construction: use ``validate_capture``."""

    adapter: str
    model_build_id: str
    compute_environment: str
    dimension: int
    prompt_ids: np.ndarray
    token_ids: np.ndarray
    finish_reason: str
    points: tuple[str, ...]
    states: Mapping[str, np.ndarray]
    row_rule: Mapping[str, str]
    row_pos: Mapping[str, np.ndarray]
    row_decides: Mapping[str, np.ndarray]
    final_norm_applied: Mapping[str, bool]
    state_dtype: str
    provenance: CaptureProvenance
    unknowns: tuple[str, ...] = ()

    @property
    def n_in(self) -> int:
        return len(self.prompt_ids)

    @property
    def n_gen(self) -> int:
        return len(self.token_ids)

    @property
    def n_rows(self) -> int:
        return len(self.token_ids)


# ---- small helpers -----------------------------------------------------------------------------


def _frozen(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(mapping))


def _check_text(value: object, path: str) -> list[ObservationIssue]:
    if isinstance(value, str) and _TEXT.fullmatch(value):
        return []
    return [_issue("OBS_TEXT", path, "must be 1-256 characters of [A-Za-z0-9._:/+@=-]")]


def _check_dimension(value: object, path: str) -> list[ObservationIssue]:
    if type(value) is int and 1 <= value <= _MAX_DIMENSION:
        return []
    return [_issue("OBS_DIM_RANGE", path, f"must be an int in 1..2**53-1, got {value!r}")]


def _check_points(names: object, path: str) -> tuple[list[ObservationIssue], bool]:
    """Issues for a tuple of point names, and whether the later checks must stop (names unreadable)."""
    if not isinstance(names, tuple) or not names:
        return [_issue("OBS_POINTS_EMPTY", path, "must be a non-empty tuple of point names")], True
    out = [_name_issue(n, f"{path}[{i}]") for i, n in enumerate(names) if _parse_point(n) is None]
    if out:
        return out, True
    return _duplicate_issues(names, path), False


def _duplicate_issues(names: Sequence[object], path: str) -> list[ObservationIssue]:
    seen: set[str] = set()
    reported: set[str] = set()
    out: list[ObservationIssue] = []
    for name in names:
        if not isinstance(name, str):
            continue
        if name in seen and name not in reported:
            reported.add(name)
            out.append(_issue("OBS_POINT_DUP", f"{path}.{name}", "point named more than once"))
        seen.add(name)
    return out


def _keys_issue(mapping: object, points: Sequence[str], path: str, not_mapping_code: str) -> ObservationIssue | None:
    if not isinstance(mapping, Mapping):
        return _issue(not_mapping_code, path, "must be a mapping keyed by point name")
    if set(mapping) != set(points):
        missing = sorted(set(points) - set(mapping))
        extra = sorted(str(k) for k in set(mapping) - set(points))
        return _issue("OBS_KEYS", path, f"keys differ from points (missing {missing}, extra {extra})")
    return None


def _collisions(points: Sequence[str], row_rule: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Pairs of points with the same ``(type(layer), layer, row_rule)``: the same space materials."""
    groups: dict[tuple[type, int | str, str], list[str]] = {}
    for name in dict.fromkeys(points):
        point = _parse_point(name)
        rule = row_rule.get(name)
        if point is None or not isinstance(rule, str):
            continue
        groups.setdefault((type(point.layer_label), point.layer_label, rule), []).append(name)
    return [(a, b) for group in groups.values() for i, a in enumerate(group) for b in group[i + 1 :]]


def _check_row_rules(
    points: Sequence[str], row_rule: Mapping[str, Any], adapter: object, path: str
) -> list[ObservationIssue]:
    """Registry, kind, adapter and collision checks. ``points`` are readable, keys equal ``points``."""
    names = tuple(dict.fromkeys(points))
    registry = ROW_RULES
    out: list[ObservationIssue] = []
    known: list[str] = []
    for name in names:
        rule = row_rule[name]
        if isinstance(rule, str) and rule in registry:
            known.append(name)
        else:
            out.append(_issue("OBS_ROW_RULE_UNKNOWN", f"{path}.{name}", f"row_rule {rule!r} is not registered"))
    for name in known:
        point = _parse_point(name)
        if point is not None and registry[row_rule[name]].kind != point.kind:
            out.append(_issue("OBS_ROW_RULE_KIND", f"{path}.{name}", "row_rule is registered for another kind"))
    for name in known:
        if registry[row_rule[name]].adapter != adapter:
            out.append(_issue("OBS_ROW_RULE_ADAPTER", f"{path}.{name}", "row_rule belongs to another adapter"))
    for a, b in _collisions(names, row_rule):
        out.append(_issue("OBS_SPACE_COLLISION", f"{path}.{b}", f"same space materials as {a}"))
    return out


def _check_final_norm(
    points: Sequence[str], mapping: Mapping[str, Any], allow_unknown: bool, path: str
) -> list[ObservationIssue]:
    """Type and definition checks of ``final_norm_applied``; keys equal ``points`` already."""
    names = tuple(dict.fromkeys(points))
    out: list[ObservationIssue] = []
    typed: list[str] = []
    for name in names:
        value = mapping[name]
        if type(value) is bool or (allow_unknown and type(value) is str and value == UNKNOWN):
            typed.append(name)
        else:
            expected = "True, False or 'unknown'" if allow_unknown else "True or False"
            out.append(_issue("OBS_FNA_TYPE", f"{path}.{name}", f"must be {expected}, got {value!r}"))
    for name in typed:
        kind = name.split(":", 1)[0]
        value = mapping[name]
        if (kind == "final_norm" and value is not True) or (kind == "mlp_out" and value is not False):
            out.append(_issue("OBS_FNA_DEFINITION", f"{path}.{name}", f"contradicts the definition of {kind}"))
    return out


def _caps_unknowns(native_dtype: object, final_norm_applied: object) -> tuple[str, ...]:
    paths: list[str] = []
    if isinstance(native_dtype, str) and native_dtype == UNKNOWN:
        paths.append("native_dtype")
    if isinstance(final_norm_applied, Mapping):
        paths.extend(f"final_norm_applied.{k}" for k, v in final_norm_applied.items() if type(v) is str and v == UNKNOWN)
    return tuple(sorted(paths))


def _unknown_paths(provenance: CaptureProvenance, state_dtype: object) -> tuple[str, ...]:
    """The ``unknowns`` of a capture: fields that are ``None`` (or ``"unknown"``), ascending."""
    paths = [
        f"provenance.{name}"
        for name in ("revision", "weights_sha256", "tokenizer_sha256", "chat_template_sha256", "special_tokens_in", "eos_ids")
        if getattr(provenance, name) is None
    ]
    runtime = provenance.runtime if isinstance(provenance.runtime, Mapping) else {}
    paths.extend(f"provenance.runtime.{key}" for key in ("mlx", "mlx_lm", "device") if runtime.get(key) is None)
    if isinstance(state_dtype, str) and state_dtype == UNKNOWN:
        paths.append("state_dtype")
    return tuple(sorted(paths))


def _ids_array(values: Any, path: str) -> np.ndarray:
    """A new read-only int64 array from a sequence of ints."""
    try:
        items = list(values)
        if not all(isinstance(v, (int, np.integer)) and not isinstance(v, bool) for v in items):
            raise TypeError
        array = np.array(items, dtype=np.int64)
    except (TypeError, ValueError, OverflowError):
        raise ObservationError((_issue("OBS_SRC_FIELD", path, "must be a sequence of ints"),)) from None
    array.setflags(write=False)
    return array


def _states_array(value: Any, path: str) -> np.ndarray:
    """A new read-only C-contiguous float32 copy. No dtype conversion: a non-float32 source is rejected."""
    if not isinstance(value, np.ndarray) or value.ndim != 2 or value.dtype != np.float32:
        raise ObservationError((_issue("OBS_SRC_FIELD", path, "must be a 2-D float32 ndarray"),))
    array = np.array(value, dtype=np.float32, order="C", copy=True)
    array.setflags(write=False)
    return array


def _ids_sha256(ids: np.ndarray) -> str:
    """SHA-256 of the ids as little-endian int64 (the rule of ``input_ids_sha256``)."""
    return hashlib.sha256(np.asarray(ids, dtype="<i8").tobytes()).hexdigest()


# ---- capabilities ------------------------------------------------------------------------------


def validate_capabilities(capabilities: Any) -> list[ObservationIssue]:
    """All problems of a capability declaration (empty list = valid). Never raises, never converts."""
    if not isinstance(capabilities, CaptureCapabilities):
        return [_issue("OBS_TYPE", "capabilities", "expected CaptureCapabilities")]
    caps = capabilities
    out: list[ObservationIssue] = []
    for name in ("adapter", "runtime", "native_dtype"):
        out.extend(_check_text(getattr(caps, name), name))
    out.extend(_check_dimension(caps.dimension, "dimension"))
    issues, stop = _check_points(caps.points, "points")
    out.extend(issues)
    if stop:
        return out
    keys = _keys_issue(caps.row_rule, caps.points, "row_rule", "OBS_KEYS")
    if keys is not None:
        out.append(keys)
    else:
        out.extend(_check_row_rules(caps.points, caps.row_rule, caps.adapter, "row_rule"))
    keys = _keys_issue(caps.final_norm_applied, caps.points, "final_norm_applied", "OBS_FNA_TYPE")
    if keys is not None:
        out.append(keys)
    else:
        out.extend(_check_final_norm(caps.points, caps.final_norm_applied, True, "final_norm_applied"))
    if caps.token_scope != TOKEN_SCOPES:
        out.append(_issue("OBS_SCOPE", "token_scope", f"must be {TOKEN_SCOPES}"))
    if not isinstance(caps.delivery, str) or caps.delivery not in DELIVERIES:
        out.append(_issue("OBS_DELIVERY", "delivery", f"must be one of {DELIVERIES}"))
    if not isinstance(caps.equivalence_check, str) or caps.equivalence_check not in EQUIVALENCE_CHECKS:
        out.append(_issue("OBS_EQUIV", "equivalence_check", f"must be one of {EQUIVALENCE_CHECKS}"))
    if caps.unknowns != _caps_unknowns(caps.native_dtype, caps.final_norm_applied):
        out.append(_issue("OBS_UNKNOWNS", "unknowns", "must list, ascending, exactly the fields whose value is 'unknown'"))
    return out


def validate_request(request: Any, capabilities: CaptureCapabilities) -> list[ObservationIssue]:
    """All problems of a capture request against valid capabilities. A point the adapter did not
    declare is rejected, never replaced by another point."""
    if validate_capabilities(capabilities):
        return [_issue("OBS_CAP_INVALID", "capabilities", "the capability declaration is not valid")]
    if not isinstance(request, CaptureRequest):
        return [_issue("OBS_TYPE", "request", "expected CaptureRequest")]
    if not isinstance(request.points, tuple) or not request.points:
        return [_issue("OBS_POINTS_EMPTY", "points", "must be a non-empty tuple of point names")]
    out: list[ObservationIssue] = []
    unreadable = {i for i, n in enumerate(request.points) if _parse_point(n) is None}
    out.extend(_name_issue(request.points[i], f"points[{i}]") for i in sorted(unreadable))
    out.extend(_duplicate_issues(request.points, "points"))
    for i, name in enumerate(request.points):
        if i not in unreadable and name not in capabilities.points:
            out.append(_issue("OBS_REQ_POINT_UNDECLARED", f"points[{i}]", f"{name} is not declared by the adapter"))
    if request.token_scope not in capabilities.token_scope:
        out.append(_issue("OBS_REQ_SCOPE", "token_scope", f"the adapter supports {capabilities.token_scope}"))
    if type(request.max_tokens) is not int or request.max_tokens < 1:
        out.append(_issue("OBS_REQ_MAX_TOKENS", "max_tokens", "must be an int >= 1"))
    if request.logit_summary is not None:
        out.append(_issue("OBS_REQ_UNSUPPORTED", "logit_summary", "logit_summary is reserved and not supported"))
    if not isinstance(request.sampling, Mapping):
        out.append(_issue("OBS_TYPE", "sampling", "must be a mapping"))
    return out


def ensure_valid(issues: Sequence[ObservationIssue]) -> None:
    """Raise ``ObservationError`` if ``issues`` is not empty."""
    if issues:
        raise ObservationError(tuple(issues))


# ---- captures ----------------------------------------------------------------------------------


def _is_int_array(value: object) -> bool:
    return isinstance(value, np.ndarray) and value.ndim == 1 and value.dtype == np.int64


def _check_provenance(prov: object) -> list[ObservationIssue]:
    if not isinstance(prov, CaptureProvenance):
        return [_issue("OBS_PROV", "provenance", "expected CaptureProvenance")]
    out: list[ObservationIssue] = []
    if not isinstance(prov.model_ref, str) or not prov.model_ref:
        out.append(_issue("OBS_PROV", "provenance.model_ref", "must be a non-empty string"))
    for name in ("weights_sha256", "tokenizer_sha256", "chat_template_sha256"):
        value = getattr(prov, name)
        if value is not None and not (isinstance(value, str) and _SHA256.fullmatch(value)):
            out.append(_issue("OBS_PROV", f"provenance.{name}", "must be None or 64 lowercase hex characters"))
    for name in ("prompt_ids_sha256", "gen_token_ids_sha256"):
        value = getattr(prov, name)
        if not (isinstance(value, str) and _SHA256.fullmatch(value)):
            out.append(_issue("OBS_PROV", f"provenance.{name}", "must be 64 lowercase hex characters"))
    runtime = prov.runtime
    if not isinstance(runtime, Mapping) or set(runtime) != {"backend", "mlx", "mlx_lm", "device"}:
        out.append(_issue("OBS_PROV", "provenance.runtime", "keys must be backend, mlx, mlx_lm, device"))
    elif runtime["backend"] != "mlx":
        out.append(_issue("OBS_PROV", "provenance.runtime.backend", "must be 'mlx'"))
    if type(prov.max_tokens) is not int or prov.max_tokens < 0:
        out.append(_issue("OBS_PROV", "provenance.max_tokens", "must be an int >= 0"))
    return out


def _check_ids(capture: ObservationCapture) -> list[ObservationIssue]:
    out: list[ObservationIssue] = []
    for name in ("prompt_ids", "token_ids"):
        value = getattr(capture, name)
        if not _is_int_array(value) or bool((value < 0).any()):
            out.append(_issue("OBS_IDS_TYPE", name, "must be a 1-D int64 ndarray without negative values"))
    return out


def validate_capture(capture: Any, capabilities: CaptureCapabilities | None = None) -> list[ObservationIssue]:
    """All problems of a capture (empty list = valid), optionally against the adapter's capabilities.

    Never raises, never converts and never changes ``capture``. Some problems stop later checks that
    could not be evaluated without the failed value; the order follows the check ids of the design.
    """
    if not isinstance(capture, ObservationCapture):
        return [_issue("OBS_TYPE", "capture", "expected ObservationCapture")]
    c = capture
    out: list[ObservationIssue] = []
    for name in ("adapter", "model_build_id", "compute_environment", "state_dtype"):
        out.extend(_check_text(getattr(c, name), name))
    issues = _check_dimension(c.dimension, "dimension")
    if issues:
        return out + issues
    issues = _check_ids(c)
    if issues:
        return out + issues
    if len(c.prompt_ids) == 0:
        return out + [_issue("OBS_PROMPT_EMPTY", "prompt_ids", "the prompt must have at least one token")]
    n_in, n_gen = len(c.prompt_ids), len(c.token_ids)
    if not isinstance(c.finish_reason, str) or c.finish_reason not in FINISH_REASONS:
        out.append(_issue("OBS_FINISH", "finish_reason", f"must be one of {FINISH_REASONS}"))
    issues, stop = _check_points(c.points, "points")
    out.extend(issues)
    if stop:
        return out
    points = c.points

    fields = ("states", "row_rule", "row_pos", "row_decides", "final_norm_applied")
    keyed: dict[str, bool] = {}
    for name in fields:
        keys = _keys_issue(getattr(c, name), points, name, "OBS_KEYS")
        keyed[name] = keys is None
        if keys is not None:
            out.append(keys)

    if keyed["states"]:
        out.extend(_check_states(c, n_gen))
    if keyed["row_rule"]:
        out.extend(_check_row_rules(points, c.row_rule, c.adapter, "row_rule"))
    out.extend(_check_rows(c, keyed, n_in, n_gen))
    if keyed["final_norm_applied"]:
        out.extend(_check_final_norm(points, c.final_norm_applied, False, "final_norm_applied"))

    provenance_issues = _check_provenance(c.provenance)
    out.extend(provenance_issues)
    if isinstance(c.provenance, CaptureProvenance):
        for name, ids in (("prompt_ids_sha256", c.prompt_ids), ("gen_token_ids_sha256", c.token_ids)):
            value = getattr(c.provenance, name)
            if isinstance(value, str) and _SHA256.fullmatch(value) and value != _ids_sha256(ids):
                out.append(_issue("OBS_PROV_MISMATCH", f"provenance.{name}", "differs from the hash of the ids"))
        # the unknown paths can only be derived from a well-formed provenance
        if not provenance_issues and c.unknowns != _unknown_paths(c.provenance, c.state_dtype):
            out.append(_issue("OBS_UNKNOWNS", "unknowns", "must list, ascending, exactly the unknown fields"))
    if capabilities is not None:
        out.extend(_check_against(c, capabilities, keyed))
    return out


def _check_states(c: ObservationCapture, n_gen: int) -> list[ObservationIssue]:
    out: list[ObservationIssue] = []
    names = tuple(dict.fromkeys(c.points))
    typed = [n for n in names if isinstance(c.states[n], np.ndarray) and c.states[n].ndim == 2]
    for name in names:
        if name not in typed:
            out.append(_issue("OBS_STATE_TYPE", f"states.{name}", "must be a 2-D ndarray"))
    # float32 by kind and size: a big-endian float32 is still a float32 and is reported as a layout problem
    floats = [n for n in typed if c.states[n].dtype.kind == "f" and c.states[n].dtype.itemsize == 4]
    for name in typed:
        if name not in floats:
            out.append(_issue("OBS_STATE_DTYPE", f"states.{name}", f"must be float32, got {c.states[name].dtype}"))
    for name in typed:
        if c.states[name].shape[1] != c.dimension:
            out.append(_issue("OBS_STATE_DIM", f"states.{name}", f"columns must equal dimension {c.dimension}"))
    for name in typed:
        if c.states[name].shape[0] != n_gen:
            out.append(_issue("OBS_STATE_ROWS", f"states.{name}", f"rows must equal n_gen {n_gen}"))
    for name in floats:
        if not bool(np.isfinite(c.states[name]).all()):
            out.append(_issue("OBS_STATE_NONFINITE", f"states.{name}", "contains NaN or Inf"))
    for name in typed:
        array = c.states[name]
        if not array.flags["C_CONTIGUOUS"] or array.dtype != array.dtype.newbyteorder("<"):
            out.append(_issue("OBS_STATE_LAYOUT", f"states.{name}", "must be C-contiguous little-endian"))
    return out


def _check_rows(c: ObservationCapture, keyed: Mapping[str, bool], n_in: int, n_gen: int) -> list[ObservationIssue]:
    out: list[ObservationIssue] = []
    expected = dict(zip(("row_pos", "row_decides"), row_positions(n_in, n_gen), strict=True))
    names = tuple(dict.fromkeys(c.points))
    arrays = [f for f in expected if keyed[f]]
    typed: list[tuple[str, str]] = []
    for field_name in arrays:
        for name in names:
            if _is_int_array(getattr(c, field_name)[name]):
                typed.append((field_name, name))
            else:
                out.append(_issue("OBS_ROW_TYPE", f"{field_name}.{name}", "must be a 1-D int64 ndarray"))
    sized: list[tuple[str, str]] = []
    for field_name, name in typed:
        if len(getattr(c, field_name)[name]) == n_gen:
            sized.append((field_name, name))
        else:
            out.append(_issue("OBS_ROW_LEN", f"{field_name}.{name}", f"length must equal n_gen {n_gen}"))
    for field_name, name in sized:
        if not np.array_equal(getattr(c, field_name)[name], expected[field_name]):
            out.append(_issue("OBS_ROW_MISMATCH", f"{field_name}.{name}", "differs from row_positions(n_in, n_gen)"))
    return out


def _check_against(c: ObservationCapture, caps: CaptureCapabilities, keyed: Mapping[str, bool]) -> list[ObservationIssue]:
    if validate_capabilities(caps):
        return [_issue("OBS_CAP_INVALID", "capabilities", "the capability declaration is not valid")]
    out: list[ObservationIssue] = []
    if c.adapter != caps.adapter:
        out.append(_issue("OBS_CAP_ADAPTER", "adapter", "differs from the declaring adapter"))
    if c.dimension != caps.dimension:
        out.append(_issue("OBS_CAP_DIM", "dimension", "differs from the declared dimension"))
    declared = [n for n in dict.fromkeys(c.points) if n in caps.points]
    for name in dict.fromkeys(c.points):
        if name not in declared:
            out.append(_issue("OBS_CAP_POINT_UNDECLARED", f"points.{name}", "the adapter did not declare this point"))
    if keyed["row_rule"]:
        for name in declared:
            if c.row_rule[name] != caps.row_rule[name]:
                out.append(_issue("OBS_CAP_ROW_RULE", f"row_rule.{name}", "differs from the declared row_rule"))
    if keyed["final_norm_applied"]:
        for name in declared:
            actual, claimed = c.final_norm_applied[name], caps.final_norm_applied[name]
            if type(claimed) is not bool or actual is not claimed:
                out.append(
                    _issue("OBS_CAP_FNA", f"final_norm_applied.{name}", "must equal the declared value (not 'unknown')")
                )
    return out


# ---- capabilities of the existing adapters -----------------------------------------------------


def llama31_mlx_capabilities(*, native_dtype: str = UNKNOWN) -> CaptureCapabilities:
    """The declaration of ``Llama31MLXCaptureProvider``: one point, ``final_norm``, 4096-D.

    ``equivalence_check="bit"`` is a statement about what was checked, not a general guarantee.
    Checked bit for bit (differences exactly 0.0, no tolerance) on real weights
    (Meta-Llama-3.1-8B-Instruct-4bit r241a666d, MLX 0.32.4, mlx-lm 0.32.2, Apple M3 Pro, float16):
    whole sequences of 44 to 105 tokens (prompts p01-p03 and g01), and, with the prefill split at
    2,048 tokens, prompts of 3,679 (p04) and 3,198 (g02) tokens: the 8 positions on each side of
    the split, the last 48 prefill positions, and 2 to 32 decode steps. Not checked: whole-sequence
    logits for p04 and g02 (only the chunked path was compared), other MLX versions or hardware,
    other weights, other prompts, lengths or seeds. The check is ``Llama31MLXAdapter.check_equivalence``.
    """
    return CaptureCapabilities(
        adapter=_LLAMA_ADAPTER,
        runtime="mlx-lm",
        dimension=_LLAMA_HIDDEN_DIMENSION,
        points=("final_norm",),
        row_rule=_frozen({"final_norm": _LLAMA_FINAL_NORM}),
        final_norm_applied=_frozen({"final_norm": True}),
        delivery="per-request",
        native_dtype=native_dtype,
        equivalence_check="bit",
        unknowns=_caps_unknowns(native_dtype, {}),
    )


def qwen35_mlx_capabilities(*, n_layers: int, dimension: int, native_dtype: str = UNKNOWN) -> CaptureCapabilities:
    """The declaration of ``Qwen35MLXCaptureProvider`` for a model of ``n_layers`` decoder layers."""
    if type(n_layers) is not int or n_layers < 1:
        raise ObservationError((_issue("OBS_CAP_ARG", "n_layers", f"must be an int >= 1, got {n_layers!r}"),))
    points = (
        *(f"block_out:{i}" for i in range(n_layers)),
        *(f"mlp_out:{i}" for i in range(n_layers)),
        "final_norm",
    )
    return CaptureCapabilities(
        adapter=_QWEN_ADAPTER,
        runtime="mlx-lm",
        dimension=dimension,
        points=points,
        row_rule=_frozen({p: _QWEN_ROW_RULE[p.split(":", 1)[0]] for p in points}),
        final_norm_applied=_frozen({p: p == "final_norm" for p in points}),
        delivery="per-request",
        native_dtype=native_dtype,
        equivalence_check="bit",
        unknowns=_caps_unknowns(native_dtype, {}),
    )


# ---- conversion of provider results ------------------------------------------------------------

_MISSING = object()
_COMMON_FIELDS = ("prompt_ids", "token_ids", "states", "finish_reason", "model_ref", "row_rule")


def _require(result: Any, names: Sequence[str]) -> None:
    missing = [n for n in names if getattr(result, n, _MISSING) is _MISSING]
    if missing:
        raise ObservationError(tuple(_issue("OBS_SRC_FIELD", n, "the provider result has no such attribute") for n in missing))


def _require_success(result: Any) -> None:
    """``ok`` is not used (a length-limit result has ``ok=False`` but valid states)."""
    if result.finish_reason not in FINISH_REASONS or getattr(result, "failure_kind", None) in _FAILED_KINDS:
        message = f"not convertible: finish_reason={result.finish_reason!r}, failure_kind={getattr(result, 'failure_kind', None)!r}"
        raise ObservationError((_issue("OBS_SRC_FAILED", "finish_reason", message),))


def _refuse_eos_among_tokens(result: Any, token_ids: np.ndarray) -> None:
    """``OBS_SRC_EOS`` if a stop id the provider reports is among the generated token ids.

    ``eos_ids`` absent or ``None`` (not reported): not checked.
    """
    eos_ids = getattr(result, "eos_ids", None)
    if eos_ids is not None and set(token_ids.tolist()) & {int(i) for i in eos_ids}:
        raise ObservationError((_issue("OBS_SRC_EOS", "token_ids", "an EOS id is among the generated token ids"),))


def _source_text_issue(result: Any, texts: set[str]) -> list[ObservationIssue]:
    if result.row_rule in texts:
        return []
    return [_issue("OBS_SRC_ROW_RULE", "row_rule", "the provider's row-rule text differs from the registered text")]


def _build_provenance(
    result: Any, prompt_ids: np.ndarray, token_ids: np.ndarray, *, qwen: bool
) -> CaptureProvenance:
    sampler = getattr(result, "sampler", None)
    if not isinstance(sampler, Mapping):
        raise ObservationError((_issue("OBS_SRC_FIELD", "sampler", "must be a mapping"),))
    special = getattr(result, "special_tokens_in", None)
    prompt_hash = _ids_sha256(prompt_ids)
    raw_eos = getattr(result, "eos_ids", None)
    eos_ids = None if raw_eos is None else tuple(int(i) for i in raw_eos)
    kwargs: Mapping[str, Any] = _empty_mapping()
    if qwen:
        kwargs = MappingProxyType(copy.deepcopy(dict(getattr(result, "chat_template_kwargs", None) or {})))
        source_hash = getattr(result, "prompt_ids_sha256", None)
        prompt_hash = source_hash if source_hash is not None else prompt_hash  # the checker compares it
    return CaptureProvenance(
        model_ref=result.model_ref,
        revision=getattr(result, "revision", None),
        weights_sha256=getattr(result, "weights_sha256", None),
        tokenizer_sha256=getattr(result, "tokenizer_sha256", None),
        chat_template_sha256=getattr(result, "chat_template_sha256", None),
        special_tokens_in=None if special is None else tuple((int(p[0]), int(p[1])) for p in special),
        prompt_ids_sha256=prompt_hash,
        gen_token_ids_sha256=_ids_sha256(token_ids),
        runtime=MappingProxyType(
            {
                "backend": "mlx",
                "mlx": getattr(result, "mlx_version", None),
                "mlx_lm": getattr(result, "mlx_lm_version", None),
                "device": getattr(result, "device", None),
            }
        ),
        sampler=MappingProxyType(copy.deepcopy(dict(sampler))),
        max_tokens=getattr(result, "max_tokens", None),  # type: ignore[arg-type]
        chat_template_kwargs=kwargs,
        eos_ids=eos_ids,
    )


def _finish(capture: ObservationCapture) -> ObservationCapture:
    ensure_valid(validate_capture(capture))
    return capture


def from_llama31(result: Any, *, model_build_id: str, compute_environment: str) -> ObservationCapture:
    """Convert a ``llama31_mlx_capture.CaptureResult`` (read by attribute; the provider is not changed).

    ``model_build_id`` and ``compute_environment`` are not in the provider result, so the caller gives
    them. Arrays are copied. The returned capture has passed ``validate_capture``.
    """
    _require(result, _COMMON_FIELDS)
    _require_success(result)
    spec = ROW_RULES.get(_LLAMA_FINAL_NORM)
    issues = _source_text_issue(result, set() if spec is None else {spec.source_text})
    try:
        states = _states_array(result.states, "states")
    except ObservationError as error:
        issues.extend(error.issues)
    ensure_valid(issues)
    prompt_ids = _ids_array(result.prompt_ids, "prompt_ids")
    token_ids = _ids_array(result.token_ids, "token_ids")
    _refuse_eos_among_tokens(result, token_ids)
    row_pos, row_decides = row_positions(len(prompt_ids), len(token_ids))
    state_dtype = getattr(result, "state_dtype", None)
    provenance = _build_provenance(result, prompt_ids, token_ids, qwen=False)
    state_dtype = UNKNOWN if state_dtype is None else state_dtype
    return _finish(
        ObservationCapture(
            adapter=_LLAMA_ADAPTER,
            model_build_id=model_build_id,
            compute_environment=compute_environment,
            dimension=int(states.shape[1]),
            prompt_ids=prompt_ids,
            token_ids=token_ids,
            finish_reason=result.finish_reason,
            points=("final_norm",),
            states=_frozen({"final_norm": states}),
            row_rule=_frozen({"final_norm": _LLAMA_FINAL_NORM}),
            row_pos=_frozen({"final_norm": row_pos}),
            row_decides=_frozen({"final_norm": row_decides}),
            final_norm_applied=_frozen({"final_norm": True}),
            state_dtype=state_dtype,
            provenance=provenance,
            unknowns=_unknown_paths(provenance, state_dtype),
        )
    )


def _qwen_positions(result: Any) -> list[tuple[ObservationPoint, str]]:
    """``(point, row_rule)`` for every provider position, or ``ObservationError`` (OBS_SRC_POSITIONS)."""
    out: list[tuple[ObservationPoint, str]] = []
    issues: list[ObservationIssue] = []
    positions = result.positions
    for index, entry in enumerate(positions if isinstance(positions, Sequence) else ()):
        path = f"positions[{index}]"
        if not isinstance(entry, Mapping) or not {"name", "kind", "layer", "row_rule"} <= set(entry):
            issues.append(_issue("OBS_SRC_POSITIONS", path, "needs name, kind, layer and row_rule"))
            continue
        try:
            layer = None if entry["layer"] == "final_norm" else entry["layer"]
            point = ObservationPoint(entry["kind"], layer)
        except ObservationError:
            issues.append(_issue("OBS_SRC_POSITIONS", path, "kind and layer do not make an observation point"))
            continue
        spec = ROW_RULES.get(entry["row_rule"]) if isinstance(entry["row_rule"], str) else None
        if entry["name"] != point.legacy_name:
            issues.append(_issue("OBS_SRC_POSITIONS", path, "name differs from the name of kind and layer"))
        elif spec is None or spec.kind != point.kind or spec.adapter != _QWEN_ADAPTER:
            issues.append(_issue("OBS_SRC_POSITIONS", path, "row_rule is not the registered rule of this kind"))
        else:
            out.append((point, entry["row_rule"]))
    if not isinstance(positions, Sequence):
        issues.append(_issue("OBS_SRC_POSITIONS", "positions", "must be a list of position entries"))
    states = result.states
    if not isinstance(states, Mapping) or set(states) != {p.legacy_name for p, _ in out} or issues:
        if not issues:
            issues.append(_issue("OBS_SRC_POSITIONS", "states", "keys differ from the names in positions"))
        raise ObservationError(tuple(issues))
    return out


def from_qwen35(result: Any, *, model_build_id: str, compute_environment: str) -> ObservationCapture:
    """Convert a ``qwen35_mlx_capture.QwenCaptureResult`` (read by attribute; the provider is not changed).

    Point names change from ``L15.mlp_out`` to ``mlp_out:15``. Arrays are copied. The returned capture
    has passed ``validate_capture``.
    """
    _require(result, (*_COMMON_FIELDS, "positions"))
    _require_success(result)
    issues = _source_text_issue(
        result, {s.source_text for s in ROW_RULES.values() if s.adapter == _QWEN_ADAPTER}
    )
    ensure_valid(issues)
    pairs = _qwen_positions(result)
    prompt_ids = _ids_array(result.prompt_ids, "prompt_ids")
    token_ids = _ids_array(result.token_ids, "token_ids")
    _refuse_eos_among_tokens(result, token_ids)
    states = {p.name: _states_array(result.states[p.legacy_name], f"states.{p.legacy_name}") for p, _ in pairs}
    names = tuple(p.name for p, _ in pairs)
    hidden = getattr(result, "hidden_size", None)
    if type(hidden) is int:
        dimension = hidden
    elif names:
        dimension = int(states[names[0]].shape[1])
        if dimension == 0:  # the provider could not read hidden_size and generated nothing
            raise ObservationError((_issue("OBS_STATE_DIM", f"states.{names[0]}", "the dimension cannot be determined"),))
    else:
        dimension = 0
    row_pos, row_decides = row_positions(len(prompt_ids), len(token_ids))
    state_dtype = getattr(result, "state_dtype", None)
    state_dtype = UNKNOWN if state_dtype is None else state_dtype
    provenance = _build_provenance(result, prompt_ids, token_ids, qwen=True)
    return _finish(
        ObservationCapture(
            adapter=_QWEN_ADAPTER,
            model_build_id=model_build_id,
            compute_environment=compute_environment,
            dimension=dimension,
            prompt_ids=prompt_ids,
            token_ids=token_ids,
            finish_reason=result.finish_reason,
            points=names,
            states=_frozen(states),
            row_rule=_frozen({p.name: rule for p, rule in pairs}),
            row_pos=_frozen({n: row_pos for n in names}),
            row_decides=_frozen({n: row_decides for n in names}),
            final_norm_applied=_frozen({p.name: p.kind == "final_norm" for p, _ in pairs}),
            state_dtype=state_dtype,
            provenance=provenance,
            unknowns=_unknown_paths(provenance, state_dtype),
        )
    )


# ---- space materials ---------------------------------------------------------------------------


def space_materials(capture: ObservationCapture, point_name: str) -> dict[str, str | int]:
    """The six materials of the space rule for one point of ``capture`` (no hash is computed).

    ``layer`` keeps its type: an int, or the string ``final_norm``.
    """
    point = _parse_point(point_name)
    if point is None or point_name not in capture.points:
        raise ObservationError((_issue("OBS_POINT_NAME", "point_name", f"{point_name!r} is not a point of the capture"),))
    return {
        "model_build_id": capture.model_build_id,
        "layer": point.layer_label,
        "row_rule": capture.row_rule[point_name],
        "compute_environment": capture.compute_environment,
        "dimension": capture.dimension,
        "space_rule": SPACE_RULE,
    }


def space_collisions(capture: ObservationCapture) -> list[tuple[str, str]]:
    """Pairs of points of ``capture`` that would get the same space materials (empty = no collision).

    Compared by ``(type(layer), layer, row_rule)``: the int ``15`` and the string ``"15"`` differ.
    """
    if not isinstance(capture.row_rule, Mapping):
        raise ObservationError((_issue("OBS_KEYS", "row_rule", "must be a mapping keyed by point name"),))
    return _collisions(capture.points, capture.row_rule)


__all__ = [
    "ALIGNMENT_DECIDES_NEXT",
    "DELIVERIES",
    "EQUIVALENCE_CHECKS",
    "FINISH_REASONS",
    "KINDS",
    "RESERVED_KINDS",
    "ROW_RULES",
    "SPACE_RULE",
    "TOKEN_SCOPES",
    "UNKNOWN",
    "CaptureCapabilities",
    "CaptureProvenance",
    "CaptureRequest",
    "ObservationCapture",
    "ObservationError",
    "ObservationIssue",
    "ObservationPoint",
    "RowRuleSpec",
    "ensure_valid",
    "from_llama31",
    "from_qwen35",
    "llama31_mlx_capabilities",
    "point_from_legacy_name",
    "point_from_name",
    "qwen35_mlx_capabilities",
    "row_positions",
    "space_collisions",
    "space_materials",
    "validate_capabilities",
    "validate_capture",
    "validate_request",
]
