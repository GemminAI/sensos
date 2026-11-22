"""common/float32-blob 0.1.0 (draft, D-100): vectors and the properties the vectors cannot say."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest
from contracts.blob import check_blob, check_float32_blob, is_non_finite_f32

ROOT = Path(__file__).resolve().parents[2] / "docs/architecture/contracts"
CASES = json.loads((ROOT / "common/vectors/blob/float32-blob.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_float32_vectors(case: dict[str, Any]) -> None:
    data = bytes.fromhex(case["data_hex"]) if "data_hex" in case else None
    codes = sorted({v.code for v in check_float32_blob(case["ref"], data)})
    assert codes == case["expect"]["codes"]
    assert (not codes) == (case["expect"]["result"] == "accept")


def test_counts_and_every_reject_has_a_code() -> None:
    accepts = [c for c in CASES if c["expect"]["result"] == "accept"]
    rejects = [c for c in CASES if c["expect"]["result"] == "reject"]
    assert (len(accepts), len(rejects)) == (15, 27)
    assert all(c["expect"]["codes"] for c in rejects)


def test_plus_and_minus_zero_have_different_hashes() -> None:
    by_id = {c["id"]: c for c in CASES}
    plus, minus = by_id["accept-plus-zero"]["ref"]["sha256"], by_id["accept-minus-zero"]["ref"]["sha256"]
    assert plus != minus
    assert plus == hashlib.sha256(struct.pack("<I", 0)).hexdigest()
    assert minus == hashlib.sha256(struct.pack("<I", 0x80000000)).hexdigest()


def test_hash_is_over_the_stored_bytes_no_normalisation() -> None:
    by_id = {c["id"]: c for c in CASES}
    for case_id in ("accept-subnormal-positive", "accept-min-subnormal", "accept-max-finite"):
        case = by_id[case_id]
        assert case["ref"]["sha256"] == hashlib.sha256(bytes.fromhex(case["data_hex"])).hexdigest()


def test_every_exponent_all_ones_pattern_class_is_rejected() -> None:
    for sign in (0, 1):
        for mantissa in (0, 1, 2, 0x200000, 0x400000, 0x400001, 0x7FFFFF):
            word = (sign << 31) | (0xFF << 23) | mantissa
            assert is_non_finite_f32(word)
            data = struct.pack("<I", word)
            ref = _ref(data)
            assert [v.code for v in check_float32_blob(ref, data)] == ["S44"]


def test_every_finite_exponent_edge_is_accepted() -> None:
    for exponent in (0, 1, 0x7F, 0xFE):
        for mantissa in (0, 1, 0x7FFFFF):
            for sign in (0, 1):
                word = (sign << 31) | (exponent << 23) | mantissa
                data = struct.pack("<I", word)
                assert check_float32_blob(_ref(data), data) == []


def test_float32_blob_with_nan_still_passes_the_old_common_blob_schema() -> None:
    """Why a new contract: common/blob 0.7.0's floatBlob has no NaN/Inf rule (it is left as it is)."""
    data = struct.pack("<I", 0x7FC00000)
    digest = hashlib.sha256(data).hexdigest()
    old = {
        "uri": "blob:sha256:" + digest, "sha256": digest, "media_type": "application/vnd.sensos.ndarray-raw",
        "dtype": "float32", "shape": [1], "byte_order": "little", "order": "C", "unit": "dimensionless",
        "comparison": {"rule": "absolute_error", "bound": {"base": 2, "exponent": -20}},
    }
    assert check_blob(old, data) == []
    assert [v.code for v in check_float32_blob(_ref(data), data)] == ["S44"]


def _ref(data: bytes) -> dict[str, Any]:
    digest = hashlib.sha256(data).hexdigest()
    return {
        "uri": "blob:sha256:" + digest, "sha256": digest, "media_type": "application/vnd.sensos.ndarray-raw",
        "dtype": "float32", "shape": [len(data) // 4], "byte_order": "little", "order": "C", "unit": "dimensionless",
    }


def test_lock_matches_schema() -> None:
    lock = json.loads(Path(__file__).with_name("contract-float32-blob.lock").read_text(encoding="utf-8"))
    (entry,) = lock["schemas"]
    path = ROOT / entry["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    assert json.loads(path.read_text(encoding="utf-8"))["$id"] == entry["id"]
