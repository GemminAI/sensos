"""Gate checks for ``nvs.meaning-measurement`` 0.1.0.

The return is a ``HiddenTrajectoryResult``. Stage 1 is the checks that were already
here: a schema failure is reported alone, and after that every failure that is
found is returned. A missing Blob is ``meaning_measurement_blob_not_supplied``
and ``check_blob`` is not called for it. Any stage-1 violation is ``FAIL`` and
stage 2 is not run.

A window-only measurement does not require the observation for stage 1. When a
token_axis parent is present, that observation envelope must be in ``stored``
(``meaning_measurement_observation_not_supplied``). Its ``binding.alignment``
must be ``decides-next/1``. The token_axis producer must be ``sensos-inference``.

Stage 2 binds ``frame_id`` to a stored ``nvs.meaning-frame``. No such frame is
``PASS_UNVERIFIED`` (``frame_binding`` / ``frame_not_supplied``), not a violation.
A stored frame that fails its own check is ``FAIL``. A frame whose Blobs are
absent is ``PASS_UNVERIFIED``. The window's ``source_trajectory`` observation is
required for the space comparison; its absence is ``PASS_UNVERIFIED``. ``D``
against the window, and ``d`` against theta, are checked whether or not that
observation is stored.
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Resource
from referencing.jsonschema import DRAFT202012

from contracts.blob import check_blob
from contracts.check import Violation
from contracts.hidden_trajectory import (
    BLOB_NOT_SUPPLIED,
    FRAME_NOT_SUPPLIED,
    OBSERVATION_NOT_SUPPLIED,
    STATUS_PASS,
    STATUS_PASS_UNVERIFIED,
    HiddenTrajectoryResult,
    Unverifiable,
)
from contracts.jcs import jcs
from contracts.meaning_frame import PAYLOAD_SCHEMA_ID as FRAME_SCHEMA_ID
from contracts.meaning_frame import check_meaning_frame
from contracts.schemas import load_schema, registry

SCHEMA_PATH = "nvs/meaning-measurement.schema.json"
PRODUCER = "meaning-mapper"
WINDOW_ROLE = "source_window"
AXIS_ROLE = "token_axis"
WINDOW_SCHEMA = ("msr.trajectory-window", "0.10.0")
WINDOW_PRODUCER = "nvs-runtime"
AXIS_SCHEMA = ("nvs.token-temporal", "0.1.0")
AXIS_PRODUCER = "sensos-inference"
ALIGNMENT = "decides-next/1"
ID_DOMAIN = "nvs.meaning-measurement/1"
_ROLES = (WINDOW_ROLE, AXIS_ROLE)
# Same symmetry window as meaning_mapper._linalg.is_spd (np.allclose atol=1e-8, default rtol).
_RTOL = 1e-5
_ATOL = 1e-8


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = load_schema(SCHEMA_PATH)
    reg = registry()
    reg = reg.with_resource(schema["$id"], Resource.from_contents(schema, DRAFT202012))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=reg)


def check_meaning_measurement(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any] | None,
    blobs: Mapping[str, bytes] | None,
) -> HiddenTrajectoryResult:
    """Stage 1 first. A violation there is ``FAIL``. Stage 2 binds the frame."""
    stored = stored or {}
    blobs = blobs or {}
    schema_error = _schema_violation(envelope.get("payload"))
    if schema_error:
        return HiddenTrajectoryResult(violations=tuple(schema_error))
    payload = envelope["payload"]
    out: list[Violation] = []
    _producer(envelope, out)
    roles, parents_ok = _roles(envelope)
    if not parents_ok:
        out.append(
            Violation(
                "meaning_measurement_parents",
                "parents must be one source_window, optional token_axis, one artifact, ordered false",
            )
        )
    _input(payload, roles, out)
    window = _parent_envelope(stored, roles.get(WINDOW_ROLE), WINDOW_ROLE, out)
    axis = None
    if AXIS_ROLE in roles:
        axis = _parent_envelope(stored, roles.get(AXIS_ROLE), AXIS_ROLE, out)
    if window is not None:
        _window(window, out)
    if axis is not None:
        _axis(axis, out)
    if window is not None and axis is not None:
        _lineage(window, axis, stored, out)
    _rows(payload, window, axis, out)
    _values(payload, blobs, out)
    _measurement_id(payload, out)
    if out:
        return HiddenTrajectoryResult(violations=tuple(out))
    return _bind_frame(payload, window, stored, blobs)


def _schema_violation(payload: Any) -> list[Violation]:
    errors = sorted(_validator().iter_errors(payload), key=lambda item: list(item.absolute_path))
    if not errors:
        return []
    first = errors[0]
    where = "/".join(str(part) for part in first.absolute_path)
    return [Violation("schema", f"payload/{where}: {first.message}")]


def _producer(envelope: Mapping[str, Any], out: list[Violation]) -> None:
    producer = envelope.get("producer")
    name = producer.get("name") if isinstance(producer, Mapping) else None
    if name != PRODUCER:
        out.append(Violation("meaning_measurement_producer", f"producer {name!r}"))


def _roles(envelope: Mapping[str, Any]) -> tuple[dict[str, str | None], bool]:
    parents = envelope.get("parents")
    found: dict[str, str | None] = {}
    if not isinstance(parents, list):
        return found, False
    ok = True
    for entry in parents:
        if not isinstance(entry, Mapping):
            ok = False
            continue
        role = entry.get("role")
        if role not in _ROLES or role in found:
            ok = False
            continue
        if entry.get("ordered") is not False:
            ok = False
        ids = entry.get("artifact_ids")
        if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str):
            ok = False
            found[role] = None
        else:
            found[role] = ids[0]
    if WINDOW_ROLE not in found or len(parents) != len(found):
        ok = False
    return found, ok


def _input(payload: Mapping[str, Any], roles: Mapping[str, str | None], out: list[Violation]) -> None:
    declared = payload["input"]
    window_id = roles.get(WINDOW_ROLE)
    if window_id is None or declared["window_artifact_id"] != window_id:
        out.append(Violation("meaning_measurement_input", "window_artifact_id differs from source_window"))
        return
    axis_declared = declared["token_axis_artifact_id"]
    has_axis = AXIS_ROLE in roles
    if has_axis:
        if axis_declared != roles.get(AXIS_ROLE):
            out.append(Violation("meaning_measurement_input", "token_axis_artifact_id differs from token_axis"))
    elif axis_declared is not None:
        out.append(Violation("meaning_measurement_input", "token_axis_artifact_id is set without a token_axis parent"))


def _parent_envelope(
    stored: Mapping[str, Any],
    artifact_id: str | None,
    role: str,
    out: list[Violation],
) -> Mapping[str, Any] | None:
    if artifact_id is None:
        return None
    held = stored.get(artifact_id)
    envelope = held.get("envelope") if isinstance(held, Mapping) else None
    if not isinstance(envelope, Mapping):
        out.append(Violation("meaning_measurement_parent_not_supplied", f"{role} is not in stored"))
        return None
    return envelope


def _window(envelope: Mapping[str, Any], out: list[Violation]) -> None:
    schema = envelope.get("payload_schema")
    ident = (schema.get("id"), schema.get("version")) if isinstance(schema, Mapping) else (None, None)
    producer = envelope.get("producer")
    name = producer.get("name") if isinstance(producer, Mapping) else None
    if ident != WINDOW_SCHEMA or name != WINDOW_PRODUCER:
        out.append(Violation("meaning_measurement_window", f"window is {ident[0]} {ident[1]} producer {name!r}"))


def _axis(envelope: Mapping[str, Any], out: list[Violation]) -> None:
    schema = envelope.get("payload_schema")
    ident = (schema.get("id"), schema.get("version")) if isinstance(schema, Mapping) else (None, None)
    producer = envelope.get("producer")
    name = producer.get("name") if isinstance(producer, Mapping) else None
    if ident != AXIS_SCHEMA or name != AXIS_PRODUCER:
        out.append(
            Violation(
                "meaning_measurement_axis",
                f"token_axis is {ident[0]} {ident[1]} producer {name!r}",
            )
        )


def _lineage(
    window: Mapping[str, Any],
    axis: Mapping[str, Any],
    stored: Mapping[str, Any],
    out: list[Violation],
) -> None:
    window_obs = _observation_id(window)
    axis_obs = _observation_id(axis)
    if window_obs is None or window_obs != axis_obs:
        out.append(Violation("meaning_measurement_lineage", "window and token_axis do not share an observation"))
        return
    held = stored.get(window_obs)
    observation = held.get("envelope") if isinstance(held, Mapping) else None
    if not isinstance(observation, Mapping):
        out.append(
            Violation(
                "meaning_measurement_observation_not_supplied",
                "the observation is not in stored",
            )
        )
        return
    alignment = _dig(observation, ("payload", "binding", "alignment"))
    if alignment != ALIGNMENT:
        out.append(Violation("meaning_measurement_alignment", f"alignment {alignment!r}"))


def _observation_id(envelope: Mapping[str, Any]) -> str | None:
    parents = envelope.get("parents")
    if not isinstance(parents, list) or len(parents) != 1 or not isinstance(parents[0], Mapping):
        return None
    ids = parents[0].get("artifact_ids")
    if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str):
        return None
    return ids[0]


def _dig(node: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = node
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _rows(
    payload: Mapping[str, Any],
    window: Mapping[str, Any] | None,
    axis: Mapping[str, Any] | None,
    out: list[Violation],
) -> None:
    if window is not None:
        length = _int_field(_dig(window, ("payload", "window", "length")))
        if length is None:
            out.append(Violation("meaning_measurement_rows", "window.length is missing"))
        else:
            for point in payload["points"]:
                rows = point["rows"]
                if rows["start"] + rows["length"] > length:
                    out.append(Violation("meaning_measurement_rows", "a point's rows pass window.length"))
                    break
    if axis is None or window is None:
        return
    origin = _int_field(_dig(window, ("payload", "origin", "length")))
    generated = _generated_n(axis)
    if origin is None or generated is None or origin != generated:
        out.append(Violation("meaning_measurement_rows", "origin.length differs from generated n"))


def _int_field(value: Any) -> int | None:
    if type(value) is int and value >= 0:
        return value
    return None


def _generated_n(axis: Mapping[str, Any]) -> int | None:
    segments = _dig(axis, ("payload", "segments"))
    if not isinstance(segments, list):
        return None
    found = [
        item.get("n")
        for item in segments
        if isinstance(item, Mapping) and item.get("origin") == "generated"
    ]
    if len(found) != 1:
        return None
    return _int_field(found[0])


def _values(payload: Mapping[str, Any], blobs: Mapping[str, bytes], out: list[Violation]) -> None:
    n = len(payload["points"])
    theta_s = payload["theta"]["shape"]
    sigma_s = payload["sigma"]["shape"]
    density_s = payload["density"]["shape"]
    d = theta_s[1] if len(theta_s) == 2 and theta_s[0] == n and theta_s[1] >= 1 else None
    if d is None or sigma_s != [n, d, d] or density_s != [n]:
        out.append(
            Violation(
                "meaning_measurement_shape",
                f"shapes are not theta [{n},d], sigma [{n},d,d], density [{n}]",
            )
        )
    arrays = {name: _blob_values(payload[name], blobs, out) for name in ("theta", "sigma", "density")}
    _finite_and_range(arrays, payload, out)


def _blob_values(
    ref: Mapping[str, Any],
    blobs: Mapping[str, bytes],
    out: list[Violation],
) -> list[float] | None:
    data = blobs.get(ref["uri"])
    if data is None:
        out.append(Violation("meaning_measurement_blob_not_supplied", f"{ref['uri']} is not supplied"))
        return None
    found = check_blob(ref, data)
    out.extend(found)
    if any(item.code in {"schema", "S25"} and "length" in item.message for item in found):
        return None
    if len(data) % 8:
        return None
    return list(struct.unpack(f"<{len(data) // 8}d", data))


def _finite_and_range(
    arrays: Mapping[str, list[float] | None],
    payload: Mapping[str, Any],
    out: list[Violation],
) -> None:
    nonfinite = False
    for values in arrays.values():
        if values is not None and any(not math.isfinite(item) for item in values):
            nonfinite = True
    if nonfinite:
        out.append(Violation("meaning_measurement_value", "a NaN or an infinity"))
    sigma = arrays["sigma"]
    if sigma is not None and not nonfinite and not _sigma_spd(sigma, payload["sigma"]["shape"]):
        out.append(Violation("meaning_measurement_sigma", "sigma is not symmetric positive definite"))
    density = arrays["density"]
    shape = payload["density"]["shape"]
    if (
        density is not None
        and not nonfinite
        and len(shape) == 1
        and shape[0] == len(density)
        and any(item < 0.0 or item > 1.0 for item in density)
    ):
        out.append(Violation("meaning_measurement_density", "density is outside [0, 1]"))


def _sigma_spd(values: list[float], shape: list[int]) -> bool:
    if len(shape) != 3 or shape[1] != shape[2] or shape[0] * shape[1] * shape[2] != len(values):
        return True
    n, d, _ = shape
    span = d * d
    for index in range(n):
        flat = values[index * span : (index + 1) * span]
        matrix = [flat[row * d : (row + 1) * d] for row in range(d)]
        if not _is_spd(matrix):
            return False
    return True


def _is_spd(matrix: list[list[float]]) -> bool:
    """Symmetry at ``is_spd``'s tolerance, then a Cholesky with a positive pivot."""
    n = len(matrix)
    for row in matrix:
        if len(row) != n:
            return False
    for i in range(n):
        for j in range(i):
            diff = abs(matrix[i][j] - matrix[j][i])
            if diff > _ATOL + _RTOL * abs(matrix[j][i]):
                return False
    sym = [[0.5 * (matrix[i][j] + matrix[j][i]) for j in range(n)] for i in range(n)]
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            total = sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                diag = sym[i][i] - total
                if diag <= 0.0:
                    return False
                lower[i][j] = math.sqrt(diag)
            else:
                lower[i][j] = (sym[i][j] - total) / lower[j][j]
    return True


def _measurement_id(payload: Mapping[str, Any], out: list[Violation]) -> None:
    expect = hashlib.sha256(
        jcs(
            {
                "domain": ID_DOMAIN,
                "frame_id": payload["frame_id"],
                "input": payload["input"],
                "points": payload["points"],
                "theta.sha256": payload["theta"]["sha256"],
                "sigma.sha256": payload["sigma"]["sha256"],
                "density.sha256": payload["density"]["sha256"],
            }
        )
    ).hexdigest()
    if payload["measurement_id"] != expect:
        out.append(Violation("meaning_measurement_id", "measurement_id differs from the recomputed id"))


def _bind_frame(
    payload: Mapping[str, Any],
    window: Mapping[str, Any] | None,
    stored: Mapping[str, Any],
    blobs: Mapping[str, bytes],
) -> HiddenTrajectoryResult:
    frames = _frames_for(stored, payload["frame_id"])
    if not frames:
        return HiddenTrajectoryResult(
            unverifiable=(Unverifiable("frame_binding", FRAME_NOT_SUPPLIED),)
        )
    checked = [(frame, check_meaning_frame(frame, stored, blobs)) for frame in frames]
    passed = [frame for frame, result in checked if result.status == STATUS_PASS]
    unverified = [frame for frame, result in checked if result.status == STATUS_PASS_UNVERIFIED]
    unverifiable: list[Unverifiable] = []
    if passed:
        chosen = passed[0]
    elif unverified:
        chosen = unverified[0]
        unverifiable.append(Unverifiable("frame_binding", BLOB_NOT_SUPPLIED))
    else:
        seen: list[str] = []
        for _, result in checked:
            for item in result.violations:
                if item.code not in seen:
                    seen.append(item.code)
        return HiddenTrajectoryResult(
            violations=(
                Violation(
                    "meaning_measurement_frame_invalid",
                    "frame failed: " + " ".join(seen),
                ),
            )
        )
    out: list[Violation] = []
    _frame_dimensions(payload, chosen["payload"], window, out)
    _frame_observation(chosen["payload"], window, stored, out, unverifiable)
    return HiddenTrajectoryResult(violations=tuple(out), unverifiable=tuple(unverifiable))


def _frames_for(stored: Mapping[str, Any], frame_id: str) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = []
    for held in stored.values():
        envelope = held.get("envelope") if isinstance(held, Mapping) else None
        if not isinstance(envelope, Mapping):
            continue
        schema = envelope.get("payload_schema")
        if not isinstance(schema, Mapping) or schema.get("id") != FRAME_SCHEMA_ID:
            continue
        body = envelope.get("payload")
        if isinstance(body, Mapping) and body.get("frame_id") == frame_id:
            found.append(envelope)
    return found


def _frame_dimensions(
    payload: Mapping[str, Any],
    frame: Mapping[str, Any],
    window: Mapping[str, Any] | None,
    out: list[Violation],
) -> None:
    depth = frame["D"]
    rank = frame["d"]
    window_depth = _int_field(_dig(window, ("payload", "dimension"))) if window is not None else None
    if window_depth != depth:
        out.append(
            Violation(
                "meaning_measurement_frame_dimension",
                "frame D differs from the window dimension",
            )
        )
    theta = payload["theta"]["shape"]
    theta_d = theta[1] if isinstance(theta, list) and len(theta) >= 2 else None
    if theta_d != rank:
        out.append(
            Violation(
                "meaning_measurement_frame_dimension",
                "frame d differs from theta",
            )
        )


def _frame_observation(
    frame: Mapping[str, Any],
    window: Mapping[str, Any] | None,
    stored: Mapping[str, Any],
    out: list[Violation],
    unverifiable: list[Unverifiable],
) -> None:
    observation = _stored_envelope(stored, _source_trajectory(window))
    if observation is None:
        unverifiable.append(Unverifiable("frame_space", OBSERVATION_NOT_SUPPLIED))
        return
    if observation.get("space_id") != frame["source_space"]:
        out.append(
            Violation(
                "meaning_measurement_frame_space",
                "observation space_id differs from source_space",
            )
        )
    if _int_field(_dig(observation, ("payload", "dimension"))) != frame["D"]:
        out.append(
            Violation(
                "meaning_measurement_frame_dimension",
                "frame D differs from the observation dimension",
            )
        )


def _source_trajectory(window: Mapping[str, Any] | None) -> str | None:
    if window is None:
        return None
    parents = window.get("parents")
    if not isinstance(parents, list):
        return None
    for entry in parents:
        if not isinstance(entry, Mapping) or entry.get("role") != "source_trajectory":
            continue
        ids = entry.get("artifact_ids")
        if isinstance(ids, list) and len(ids) == 1 and isinstance(ids[0], str):
            return ids[0]
        return None
    return None


def _stored_envelope(stored: Mapping[str, Any], artifact_id: str | None) -> Mapping[str, Any] | None:
    if artifact_id is None:
        return None
    held = stored.get(artifact_id)
    envelope = held.get("envelope") if isinstance(held, Mapping) else None
    if not isinstance(envelope, Mapping):
        return None
    return envelope
