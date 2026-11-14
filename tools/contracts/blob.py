"""Blob references (``common/blob.schema.json``, design v0.7.1 section 7.1) and
the checks on a Blob's bytes that a schema cannot express.

``check_blob(ref, data)`` returns violation codes (empty = accept):
``schema`` (reported alone), ``S34`` (uri hex != sha256), ``S24`` / ``S25``
(sha256 or length of an int / float Blob), ``S36`` (-2^63 without
``undefined: "int64_min"``), ``count_negative`` (negative value in a count Blob).
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from contracts.check import Violation
from contracts.schemas import validator

INT64_MIN = -(2**63)
ITEMSIZE = {"int64": 8, "float32": 4, "float64": 8}


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return validator("common/blob.schema.json")


def decode_int64(data: bytes) -> list[int]:
    return list(struct.unpack(f"<{len(data) // 8}q", data[: len(data) // 8 * 8]))


def check_blob(ref: Mapping[str, Any], data: bytes | None) -> list[Violation]:
    errors = sorted(_validator().iter_errors(ref), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        return [Violation("schema", f"{'/'.join(str(p) for p in first.absolute_path)}: {first.message}")]
    out: list[Violation] = []
    if ref["uri"] != "blob:sha256:" + ref["sha256"]:
        out.append(Violation("S34", "uri hex differs from sha256"))
    if data is None:
        return out
    integer = ref["dtype"] == "int64"
    code = "S24" if integer else "S25"
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        out.append(Violation(code, "sha256 differs from the bytes"))
    if len(data) != math.prod(ref["shape"]) * ITEMSIZE[ref["dtype"]]:
        out.append(Violation(code, "length differs from shape x itemsize"))
        return out
    if integer:
        values = decode_int64(data)
        declared = ref.get("undefined") == "int64_min"
        if INT64_MIN in values and not declared:
            out.append(Violation("S36", "-2^63 without undefined: int64_min"))
        if ref["quantization"] is None and any(v < 0 for v in values if v != INT64_MIN or not declared):
            out.append(Violation("count_negative", "negative value in a count Blob"))
    return out


# --------------------------------------------------------------- float32 Blob (D-100)

_F32_VALIDATOR: Draft202012Validator | None = None


def is_non_finite_f32(word: int) -> bool:
    """binary32 bits: exponent all ones = NaN (any mantissa != 0, either sign) or +-Inf."""
    return (word >> 23) & 0xFF == 0xFF


def check_float32_blob(ref: Mapping[str, Any], data: bytes | None) -> list[Violation]:
    """``common/float32-blob.schema.json`` and the checks on the bytes (no float conversion).

    Codes (provisional numbers): ``schema`` (alone), ``S34`` (uri hex != sha256), ``S42``
    (sha256 differs from the bytes), ``S43`` (length != prod(shape) x 4), ``S44`` (a NaN or
    +-Inf bit pattern).
    """
    global _F32_VALIDATOR
    if _F32_VALIDATOR is None:
        _F32_VALIDATOR = validator("common/float32-blob.schema.json")
    errors = sorted(_F32_VALIDATOR.iter_errors(ref), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        return [Violation("schema", f"{'/'.join(str(p) for p in first.absolute_path)}: {first.message}")]
    out: list[Violation] = []
    if ref["uri"] != "blob:sha256:" + ref["sha256"]:
        out.append(Violation("S34", "uri hex differs from sha256"))
    if data is None:
        return out
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        out.append(Violation("S42", "sha256 differs from the bytes"))
    if len(data) != math.prod(ref["shape"]) * 4:
        out.append(Violation("S43", "length differs from shape x 4"))
        return out
    words = struct.unpack(f"<{len(data) // 4}I", data)
    if any(is_non_finite_f32(w) for w in words):
        out.append(Violation("S44", "NaN or Inf bit pattern"))
    return out
