"""Gate checks for ``nvs.meaning-frame`` 0.1.0.

The return is a ``HiddenTrajectoryResult``. A schema failure is reported alone.
After that, every failure that is found is returned. A missing Blob is
UNVERIFIABLE ``frame_content`` / ``blob_not_supplied`` and ``check_blob`` is
not called for it. ``frame_id`` is the sha256 of the raw Blob bytes under
``meaning-mapper.window-frame/1``; the floats are not recomputed.
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
from contracts.hidden_trajectory import BLOB_NOT_SUPPLIED, HiddenTrajectoryResult, Unverifiable
from contracts.schemas import load_schema, registry

SCHEMA_PATH = "nvs/meaning-frame.schema.json"
PAYLOAD_SCHEMA_ID = "nvs.meaning-frame"
PAYLOAD_SCHEMA_VERSION = "0.1.0"
PRODUCER = "meaning-mapper"
KIND = "interpretation"
CONTENT_RULE = "meaning-mapper.window-frame/1"
_ARRAYS = ("mu", "basis", "sigma0")


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = load_schema(SCHEMA_PATH)
    reg = registry()
    reg = reg.with_resource(schema["$id"], Resource.from_contents(schema, DRAFT202012))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=reg)


def check_meaning_frame(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any] | None,
    blobs: Mapping[str, bytes] | None,
) -> HiddenTrajectoryResult:
    """Schema first (alone if it fails); then every check that fails."""
    del stored
    blobs = blobs or {}
    schema_error = _schema_violation(envelope.get("payload"))
    if schema_error:
        return HiddenTrajectoryResult(violations=tuple(schema_error))
    payload = envelope["payload"]
    out: list[Violation] = []
    _producer(envelope, out)
    supplied: dict[str, bytes] = {}
    missing = False
    for name in _ARRAYS:
        data = _blob(payload[name], blobs, out)
        if data is None:
            missing = True
        else:
            supplied[name] = data
    _shape(payload, out)
    _finite(payload, supplied, out)
    if not missing:
        _frame_id(payload, supplied, out)
        _sigma0(payload, supplied, out)
    unverifiable = (Unverifiable("frame_content", BLOB_NOT_SUPPLIED),) if missing else ()
    return HiddenTrajectoryResult(violations=tuple(out), unverifiable=unverifiable)


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
    if envelope.get("kind") != KIND or name != PRODUCER:
        out.append(Violation("meaning_frame_producer", f"kind {envelope.get('kind')!r} producer {name!r}"))


def _blob(
    ref: Mapping[str, Any],
    blobs: Mapping[str, bytes],
    out: list[Violation],
) -> bytes | None:
    data = blobs.get(ref["uri"])
    if data is None:
        return None
    out.extend(check_blob(ref, data))
    return data


def _shape(payload: Mapping[str, Any], out: list[Violation]) -> None:
    d = payload["d"]
    depth = payload["D"]
    expected = {
        "mu": [depth],
        "basis": [d, depth],
        "sigma0": [d, d],
    }
    if any(payload[name]["shape"] != shape for name, shape in expected.items()):
        out.append(
            Violation(
                "meaning_frame_shape",
                f"shapes are not mu [{depth}], basis [{d},{depth}], sigma0 [{d},{d}]",
            )
        )


def _aligned(ref: Mapping[str, Any], data: bytes) -> list[float] | None:
    count = math.prod(ref["shape"])
    if len(data) != count * 8:
        return None
    return list(struct.unpack(f"<{count}d", data))


def _finite(payload: Mapping[str, Any], supplied: Mapping[str, bytes], out: list[Violation]) -> None:
    nonfinite = False
    for name, data in supplied.items():
        values = _aligned(payload[name], data)
        if values is not None and any(not math.isfinite(item) for item in values):
            nonfinite = True
    if nonfinite:
        out.append(Violation("meaning_frame_nonfinite", "a NaN or an infinity"))


def _frame_id(payload: Mapping[str, Any], supplied: Mapping[str, bytes], out: list[Violation]) -> None:
    chunks = [f"{CONTENT_RULE}\n".encode("ascii")]
    for name in _ARRAYS:
        shape = payload[name]["shape"]
        dims = " ".join(str(dim) for dim in shape)
        chunks.append(f"{name} {len(shape)} {dims}\n".encode("ascii"))
        chunks.append(supplied[name])
    expect = "frame:sha256:" + hashlib.sha256(b"".join(chunks)).hexdigest()
    if payload["frame_id"] != expect:
        out.append(Violation("meaning_frame_id_mismatch", "frame_id differs from the recomputed id"))


def _sigma0(payload: Mapping[str, Any], supplied: Mapping[str, bytes], out: list[Violation]) -> None:
    values = _aligned(payload["sigma0"], supplied["sigma0"])
    if values is None or any(not math.isfinite(item) for item in values):
        return
    d = payload["d"]
    if payload["sigma0"]["shape"] != [d, d] or len(values) != d * d:
        return
    matrix = [values[row * d : (row + 1) * d] for row in range(d)]
    # Imported lazily: meaning_measurement imports this module for stage 2.
    from contracts.meaning_measurement import _is_spd

    if not _is_spd(matrix):
        out.append(Violation("meaning_frame_sigma0", "sigma0 is not symmetric positive definite"))
