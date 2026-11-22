"""nvs.meaning-frame 0.1.0: the payload checks, and the gate_nvs branch.

The fixed frame_id is meaning-mapper ``frame_content_id`` at ``8dbcf32`` for
mu ``[1.0, -0.0, 2.5]``, basis ``[[1, 0, 0], [0, 1, 3]]``, sigma0 ``[[2, 0.5], [0.5, 2]]``.
"""

from __future__ import annotations

import copy
import hashlib
import math
import struct
from typing import Any

from jsonschema import Draft202012Validator

from contracts.check import Violation
from contracts.gate_nvs import check_nvs_payload
from contracts.hidden_trajectory import STATUS_FAIL, STATUS_PASS, STATUS_PASS_UNVERIFIED, Unverifiable
from contracts.meaning_frame import check_meaning_frame
from contracts.schemas import load_schema

_SPACE = "hid:" + "ab" * 32
_FIXED = "frame:sha256:a6beaa1ff6c1823a75319fb2d27027f6d6cded2e562875d87014a50b57004e2c"
_RULE = "meaning-mapper.window-frame/1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content_id(parts: list[tuple[str, list[int], bytes]]) -> str:
    chunks = [f"{_RULE}\n".encode("ascii")]
    for name, shape, data in parts:
        dims = " ".join(str(dim) for dim in shape)
        chunks.append(f"{name} {len(shape)} {dims}\n".encode("ascii"))
        chunks.append(data)
    return "frame:sha256:" + _sha(b"".join(chunks))


def _ref(values: list[float], shape: list[int]) -> tuple[dict[str, Any], bytes]:
    data = struct.pack(f"<{len(values)}d", *values)
    digest = _sha(data)
    ref = {
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
    return ref, data


def _world(
    mu: list[float] | None = None,
    basis: list[float] | None = None,
    sigma0: list[float] | None = None,
    *,
    d: int = 2,
    depth: int = 3,
    frame_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    mu = [1.0, -0.0, 2.5] if mu is None else mu
    basis = [1.0, 0.0, 0.0, 0.0, 1.0, 3.0] if basis is None else basis
    sigma0 = [2.0, 0.5, 0.5, 2.0] if sigma0 is None else sigma0
    mu_ref, mu_bytes = _ref(mu, [depth])
    basis_ref, basis_bytes = _ref(basis, [d, depth])
    sigma_ref, sigma_bytes = _ref(sigma0, [d, d])
    parts = [("mu", [depth], mu_bytes), ("basis", [d, depth], basis_bytes), ("sigma0", [d, d], sigma_bytes)]
    payload = {
        "frame_id": frame_id if frame_id is not None else _content_id(parts),
        "content_rule": _RULE,
        "d": d,
        "D": depth,
        "source_space": _SPACE,
        "mu": mu_ref,
        "basis": basis_ref,
        "sigma0": sigma_ref,
    }
    envelope = {
        "kind": "interpretation",
        "payload_schema": {"id": "nvs.meaning-frame", "version": "0.1.0"},
        "payload": payload,
        "producer": {"name": "meaning-mapper", "version": "0.1.0", "build": "mm"},
    }
    blobs = {mu_ref["uri"]: mu_bytes, basis_ref["uri"]: basis_bytes, sigma_ref["uri"]: sigma_bytes}
    return envelope, blobs


def _codes(envelope: dict[str, Any], blobs: dict[str, bytes]) -> list[str]:
    return [item.code for item in check_meaning_frame(envelope, {}, blobs).violations]


def test_the_schema_is_draft_2020_12() -> None:
    schema = load_schema("nvs/meaning-frame.schema.json")
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == "sensos:contracts/nvs/meaning-frame/0.1.0"
    assert "0.1.0 確定" in schema["title"]


def test_a_correct_frame_passes() -> None:
    envelope, blobs = _world()
    result = check_meaning_frame(envelope, {}, blobs)
    assert result.status == STATUS_PASS
    assert result.violations == ()
    assert result.unverifiable == ()


def test_the_signed_zero_frame_id_matches_meaning_mapper() -> None:
    envelope, blobs = _world()
    assert envelope["payload"]["frame_id"] == _FIXED
    assert struct.pack("<d", -0.0)[7] == 0x80
    result = check_meaning_frame(envelope, {}, blobs)
    assert result.status == STATUS_PASS


def test_a_schema_failure_is_reported_alone() -> None:
    envelope, blobs = _world()
    envelope["payload"]["extra"] = 1
    result = check_meaning_frame(envelope, {}, blobs)
    assert result.status == STATUS_FAIL
    assert [item.code for item in result.violations] == ["schema"]
    assert result.violations[0].message.startswith("payload/")


def test_a_producer_that_is_not_meaning_mapper_is_refused() -> None:
    envelope, blobs = _world()
    envelope["producer"]["name"] = "nvs-runtime"
    assert _codes(envelope, blobs) == ["meaning_frame_producer"]


def test_a_shape_that_disagrees_with_d_and_depth_is_refused() -> None:
    envelope, blobs = _world()
    envelope["payload"]["D"] = 4
    assert _codes(envelope, blobs) == ["meaning_frame_shape"]


def test_a_nan_is_refused() -> None:
    envelope, blobs = _world(mu=[math.nan, -0.0, 2.5])
    assert _codes(envelope, blobs) == ["meaning_frame_nonfinite"]


def test_a_frame_id_that_was_not_recomputed_is_refused() -> None:
    envelope, blobs = _world(frame_id="frame:sha256:" + "b" * 64)
    assert _codes(envelope, blobs) == ["meaning_frame_id_mismatch"]


def test_an_asymmetric_sigma0_is_refused() -> None:
    envelope, blobs = _world(sigma0=[2.0, 0.5, 0.0, 2.0])
    assert _codes(envelope, blobs) == ["meaning_frame_sigma0"]


def test_a_sigma0_that_is_not_positive_definite_is_refused() -> None:
    envelope, blobs = _world(sigma0=[1.0, 0.0, 0.0, -1.0])
    assert _codes(envelope, blobs) == ["meaning_frame_sigma0"]


def test_a_blob_whose_sha256_differs_is_refused() -> None:
    envelope, blobs = _world()
    uri = envelope["payload"]["mu"]["uri"]
    raw = bytearray(blobs[uri])
    raw[0] ^= 0x01
    blobs[uri] = bytes(raw)
    result = check_meaning_frame(envelope, {}, blobs)
    assert result.status == STATUS_FAIL
    assert "S25" in [item.code for item in result.violations]


def test_a_missing_blob_is_unverified_not_a_violation() -> None:
    envelope, blobs = _world()
    del blobs[envelope["payload"]["mu"]["uri"]]
    result = check_meaning_frame(envelope, {}, blobs)
    assert result.status == STATUS_PASS_UNVERIFIED
    assert result.violations == ()
    assert result.unverifiable == (Unverifiable("frame_content", "blob_not_supplied"),)


def test_an_unknown_frame_version_is_s39() -> None:
    envelope, blobs = _world()
    assert check_nvs_payload(envelope, {}, blobs).status == STATUS_PASS
    other = copy.deepcopy(envelope)
    other["payload_schema"] = {"id": "nvs.meaning-frame", "version": "0.2.0"}
    found = check_nvs_payload(other, {}, blobs)
    assert [(item.code, item.message) for item in found.violations] == [
        ("S39", "unknown payload_schema nvs.meaning-frame 0.2.0")
    ]
    assert isinstance(found.violations[0], Violation)
