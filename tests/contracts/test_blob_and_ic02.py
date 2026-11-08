"""Blob vectors (S24, S34, S36), and the IC-02 / Gate checks (S35-S39)."""

from __future__ import annotations

import copy
import hashlib
import json
import struct
from typing import Any

import pytest
from contracts.blob import INT64_MIN, check_blob
from contracts.gate import PAYLOAD_SCHEMAS, check_payload
from contracts.ic02 import SERIES, expected_undefined, verdict_state
from make_vectors import VECTORS
from test_schemas import CAL, INPUT_REF, PAIR, QUANT, SERIES_UNITS, _single

U = INT64_MIN
BLOB_VECTORS = json.loads((VECTORS / "blob" / "blob-refs.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", BLOB_VECTORS, ids=[c["id"] for c in BLOB_VECTORS])
def test_blob_vectors(case: dict[str, Any]) -> None:
    data = bytes.fromhex(case["data_hex"]) if "data_hex" in case else None
    codes = sorted({v.code for v in check_blob(case["ref"], data)})
    assert codes == case["expect"]["codes"]
    assert (not codes) == (case["expect"]["result"] == "accept")


def test_blob_vector_counts() -> None:
    accepts = sum(1 for c in BLOB_VECTORS if c["expect"]["result"] == "accept")
    assert (accepts, len(BLOB_VECTORS) - accepts) == (8, 24)
    codes = {code for c in BLOB_VECTORS for code in c["expect"]["codes"]}
    assert {"schema", "S34", "S24", "S25", "S36", "count_negative"} <= codes


# ---------------------------------------------------------------- IC-02 sample

T = 4
VALUES: dict[str, list[int]] = {  # t = 0..3; thresholds below: eps, delta, w_min = 1, no codebook
    "displacement_mean": [U, 100, 200, 300],
    "displacement_median": [U, 100, 150, 250],
    "displacement_longest_sub_delta_run": [U, 0, 1, 1],
    "recurrence_pair_fraction": [U, U, 0, 1 << 28],
    "recurrence_return_count": [0, 0, 0, 1],
    "recurrence_return_rate": [0, 0, 0, 1 << 28],
    "diversity_cell_entropy": [U, U, U, U],
    "diversity_participation_ratio": [U, 1 << 30, 1 << 30, 3 << 29],
    "persistence_longest_stay": [1, 1, 2, 2],
    "persistence_dominant_cell_share": [1 << 30, 1 << 29, 2 << 28, 1 << 29],
}


def _ref(name: str, values: list[int]) -> tuple[dict[str, Any], bytes]:
    data = struct.pack(f"<{len(values)}q", *values)
    digest = hashlib.sha256(data).hexdigest()
    unit, real = SERIES_UNITS[name]
    ref: dict[str, Any] = {
        "uri": "blob:sha256:" + digest,
        "sha256": digest,
        "media_type": "application/vnd.sensos.ndarray-raw",
        "dtype": "int64",
        "shape": [len(values)],
        "byte_order": "little",
        "order": "C",
        "unit": unit,
        "quantization": copy.deepcopy(QUANT) if real else None,
    }
    if U in values:
        ref["undefined"] = "int64_min"
    return ref, data


def single_world() -> tuple[dict[str, Any], dict[str, bytes]]:
    payload = _single()
    payload["input_ref"] = {**INPUT_REF, "length": T}
    payload["thresholds"]["source"] = {"epsilon": "explicit", "delta": "explicit", "w_min": "explicit"}
    payload["calibration"] = None
    blobs: dict[str, bytes] = {}
    series: dict[str, Any] = {}
    for name, values in VALUES.items():
        series[name], data = _ref(name, values)
        blobs[series[name]["uri"]] = data
    payload["series"] = series
    last = {name: (None if v[-1] == U else v[-1]) for name, v in VALUES.items()}
    for name, (group, key) in SERIES.items():
        payload["metrics"][group][key] = last[name]
    envelope = {
        "payload_schema": {"id": "msr.geometry-measurement", "version": "0.7.0"},
        "payload": payload,
        "parents": [{"role": "trajectory", "ordered": False, "artifact_ids": ["art:" + "0" * 64]}],
    }
    return envelope, blobs


def codes(envelope: dict[str, Any], blobs: dict[str, bytes] | None = None, stored: Any = None) -> set[str]:
    return {v.code for v in check_payload(envelope, stored, blobs)}


def test_valid_single_passes_every_check() -> None:
    envelope, blobs = single_world()
    assert check_payload(envelope, {}, blobs) == []


def _replace(envelope: dict[str, Any], blobs: dict[str, bytes], name: str, values: list[int]) -> None:
    ref, data = _ref(name, values)
    old = envelope["payload"]["series"][name]
    envelope["payload"]["series"][name] = ref
    blobs.pop(old["uri"], None)
    blobs[ref["uri"]] = data


def test_s35_shape_and_key_set() -> None:
    envelope, blobs = single_world()
    _replace(envelope, blobs, "displacement_mean", [U, 1, 2])  # T-1 elements
    assert "S35" in codes(envelope, blobs)
    envelope, blobs = single_world()
    del envelope["payload"]["series"]["recurrence_return_rate"]
    assert "schema" in codes(envelope, blobs)  # key set is the schema's job


def test_s36_undefined_only_where_the_contract_says() -> None:
    envelope, blobs = single_world()
    _replace(envelope, blobs, "displacement_mean", [U, 100, U, 300])  # extra undefined
    assert "S36" in codes(envelope, blobs)
    envelope, blobs = single_world()
    _replace(envelope, blobs, "displacement_mean", [0, 100, 200, 300])  # t=0 must be undefined
    assert "S36" in codes(envelope, blobs)
    envelope, blobs = single_world()
    ref = envelope["payload"]["series"]["diversity_cell_entropy"]
    ref.pop("undefined")  # -2^63 present but not declared
    assert "S36" in codes(envelope, blobs)


def test_s37_last_element_equals_metrics() -> None:
    envelope, blobs = single_world()
    envelope["payload"]["metrics"]["displacement"]["mean"] = 301
    assert codes(envelope, blobs) == {"S37"}
    envelope, blobs = single_world()
    envelope["payload"]["metrics"]["recurrence"]["return_count"] = None
    assert codes(envelope, blobs) == {"S37"}
    envelope, blobs = single_world()
    envelope["payload"]["metrics"]["recurrence"]["return_count"] = 2
    assert codes(envelope, blobs) == {"S37"}


def test_s34_s24_inside_a_payload() -> None:
    envelope, blobs = single_world()
    ref = envelope["payload"]["series"]["displacement_mean"]
    ref["uri"] = "blob:sha256:" + "0" * 64
    blobs["blob:sha256:" + "0" * 64] = blobs.pop("blob:sha256:" + ref["sha256"])
    assert codes(envelope, blobs) == {"S34"}
    envelope, blobs = single_world()
    uri = envelope["payload"]["series"]["displacement_mean"]["uri"]
    blobs[uri] = blobs[uri][:-8] + struct.pack("<q", 5)
    assert "S24" in codes(envelope, blobs)


def test_expected_undefined_table() -> None:
    th = {"epsilon": None, "delta": None, "w_min": None}
    full = set(range(5))
    assert expected_undefined("recurrence_pair_fraction", 5, th, False) == full
    assert expected_undefined("recurrence_return_count", 5, th, False) == full
    assert expected_undefined("displacement_longest_sub_delta_run", 5, th, False) == full
    assert expected_undefined("persistence_longest_stay", 5, th, False) == full
    assert expected_undefined("persistence_longest_stay", 5, th, True) == set()
    assert expected_undefined("diversity_cell_entropy", 5, th, True) == set()
    th2 = {"epsilon": 5, "delta": 5, "w_min": 0}
    assert expected_undefined("recurrence_pair_fraction", 5, th2, False) == {0}
    assert expected_undefined("recurrence_pair_fraction", 2, {**th2, "w_min": 9}, False) == {0, 1}
    assert expected_undefined("persistence_longest_stay", 5, th2, False) == set()
    assert expected_undefined("diversity_participation_ratio", 5, th2, False) == {0}


# --------------------------------------------------------------------- pair

LO, HI = 1 << 30, 2 << 30
CALIBRATION = {"envelope": {"payload": {"values": {"noise_floor_lower": LO, "noise_floor_upper": HI}}}}


def pair_envelope(distance: int, state: str, calibrated: bool = True) -> dict[str, Any]:
    payload = copy.deepcopy(PAIR)
    payload["distance"]["value"] = distance
    payload["verdict"]["state"] = state
    payload["calibration"] = CAL if calibrated else None
    return {
        "payload_schema": {"id": "msr.geometry-measurement", "version": "0.7.0"},
        "payload": payload,
        "parents": [],
    }


STORED = {CAL["artifact_id"]: CALIBRATION}
TABLE = [
    (0, "STAGNANT"),
    (LO - 1, "STAGNANT"),
    (LO, "NOISE_FLOOR_INTERNAL"),  # boundary: inside the noise band
    (LO + 1, "NOISE_FLOOR_INTERNAL"),
    (HI, "NOISE_FLOOR_INTERNAL"),  # boundary
    (HI + 1, "STRUCTURAL_SHIFT_DETECTED"),
]


@pytest.mark.parametrize(("d", "state"), TABLE)
def test_s38_boundary_table(d: int, state: str) -> None:
    assert verdict_state(d, CALIBRATION["envelope"]["payload"]) == state
    assert check_payload(pair_envelope(d, state), STORED, {}) == []
    wrong = next(s for _, s in TABLE if s != state)
    assert {v.code for v in check_payload(pair_envelope(d, wrong), STORED, {})} == {"S38"}


def test_s38_uncalibrated_and_unknown_calibration() -> None:
    assert check_payload(pair_envelope(5, "UNCALIBRATED", calibrated=False), {}, {}) == []
    assert verdict_state(5, None) == "UNCALIBRATED"
    assert {v.code for v in check_payload(pair_envelope(5, "STAGNANT"), {}, {})} == {"calibration_unknown"}


# ---------------------------------------------------------------------- S39


def test_s39_unknown_payload_schema_versions_are_refused() -> None:
    envelope, blobs = single_world()
    assert set(PAYLOAD_SCHEMAS) == {("msr.geometry-measurement", "0.7.0"), ("msr.calibration", "0.7.0")}
    for ident, version in (
        ("msr.geometry-measurement", "0.6.2"),
        ("msr.geometry-measurement", "1.0.0"),  # IC-00's version is not a payload version
        ("msr.calibration", "0.6.1"),
        ("nope", "0.7.0"),
    ):
        bad = {**envelope, "payload_schema": {"id": ident, "version": version}}
        assert codes(bad, blobs) == {"S39"}


def test_calibration_payload_goes_through_its_schema() -> None:
    from test_schemas import _cal

    ok = {"payload_schema": {"id": "msr.calibration", "version": "0.7.0"}, "payload": _cal(), "parents": []}
    assert check_payload(ok) == []
    bad = {**ok, "payload": {**_cal(), "extra": 1}}
    assert {v.code for v in check_payload(bad)} == {"schema"}
