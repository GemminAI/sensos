"""nvs.meaning-measurement 0.1.0: the schema is Draft 2020-12 and resolves the blob contract."""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Resource
from referencing.jsonschema import DRAFT202012

from contracts.schemas import load_schema, registry

SCHEMA_PATH = "nvs/meaning-measurement.schema.json"
_FRAME = "frame:sha256:" + "ab" * 32


def _validator() -> Draft202012Validator:
    schema = load_schema(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    reg = registry().with_resource(schema["$id"], Resource.from_contents(schema, DRAFT202012))
    return Draft202012Validator(schema, registry=reg)


def _floats(shape: list[int]) -> dict[str, Any]:
    count = math.prod(shape)
    data = struct.pack(f"<{count}d", *([0.0] * count))
    digest = hashlib.sha256(data).hexdigest()
    return {
        "uri": "blob:sha256:" + digest,
        "sha256": digest,
        "media_type": "application/vnd.sensos.ndarray-raw",
        "dtype": "float64",
        "shape": shape,
        "byte_order": "little",
        "order": "C",
        "comparison": {"rule": "absolute_error", "bound": {"base": 2, "exponent": -40}},
        "unit": "1",
    }


def _payload() -> dict[str, Any]:
    return {
        "measurement_id": "ab" * 32,
        "frame_id": _FRAME,
        "input": {
            "kind": "window",
            "window_artifact_id": "art:" + "a" * 64,
            "token_axis_artifact_id": None,
        },
        "points": [{"rows": {"start": 0, "length": 1}}],
        "theta": _floats([1, 2]),
        "sigma": _floats([1, 2, 2]),
        "density": _floats([1]),
    }


def test_the_schema_is_draft_2020_12() -> None:
    schema = load_schema(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == "sensos:contracts/nvs/meaning-measurement/0.1.0"
    assert "0.1.0 確定" in schema["title"]


def test_a_float64_example_validates_with_the_blob_contract() -> None:
    errors = list(_validator().iter_errors(_payload()))
    assert errors == []


def test_float32_is_rejected() -> None:
    payload = _payload()
    payload["theta"]["dtype"] = "float32"
    assert list(_validator().iter_errors(payload))


def test_zero_points_are_rejected() -> None:
    payload = _payload()
    payload["points"] = []
    assert list(_validator().iter_errors(payload))


def test_another_input_kind_is_rejected() -> None:
    payload = _payload()
    payload["input"]["kind"] = "token"
    assert list(_validator().iter_errors(payload))


def test_a_frame_id_must_be_a_content_address() -> None:
    for frame_id in (
        "f",
        "frame:sha256:" + "AB" * 32,
        "frame:sha256:" + "a" * 63,
        "frame:sha256:" + "a" * 65,
        "id:sha256:" + "a" * 64,
    ):
        payload = _payload()
        payload["frame_id"] = frame_id
        assert list(_validator().iter_errors(payload)), frame_id


def test_an_extra_property_is_rejected() -> None:
    payload = _payload()
    payload["extra"] = 1
    assert list(_validator().iter_errors(payload))
