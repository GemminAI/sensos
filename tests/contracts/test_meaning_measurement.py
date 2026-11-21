"""nvs.meaning-measurement 0.1.0: the payload checks, and the gate_nvs branch."""

from __future__ import annotations

import copy
import hashlib
import math
import struct
from typing import Any

from contracts.gate_nvs import check_nvs_payload
from contracts.jcs import jcs
from contracts.meaning_measurement import check_meaning_measurement

_OBS = "art:" + "1" * 64
_WINDOW = "art:" + "a" * 64
_AXIS = "art:" + "b" * 64
_D = 2


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _measurement_id(payload: dict[str, Any]) -> str:
    body = {
        "domain": "nvs.meaning-measurement/1",
        "frame_id": payload["frame_id"],
        "input": payload["input"],
        "points": payload["points"],
        "theta.sha256": payload["theta"]["sha256"],
        "sigma.sha256": payload["sigma"]["sha256"],
        "density.sha256": payload["density"]["sha256"],
    }
    return _sha(jcs(body))


def _ref(values: list[float], shape: list[int]) -> tuple[dict[str, Any], bytes]:
    data = struct.pack(f"<{len(values)}d", *values) if values else b""
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


def _identity(n: int) -> list[float]:
    values: list[float] = []
    for _ in range(n):
        for row in range(_D):
            for col in range(_D):
                values.append(1.0 if row == col else 0.0)
    return values


def _replace(
    payload: dict[str, Any],
    blobs: dict[str, bytes],
    name: str,
    values: list[float],
    shape: list[int],
) -> None:
    ref, data = _ref(values, shape)
    blobs.pop(payload[name]["uri"], None)
    payload[name] = ref
    blobs[ref["uri"]] = data
    payload["measurement_id"] = _measurement_id(payload)


def _world(
    n: int = 1,
    *,
    axis: bool = False,
    observation: bool = False,
    alignment: str = "decides-next/1",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
    length = max(n, 1)
    if n == 1:
        points = [{"rows": {"start": 0, "length": length}}]
    else:
        points = [{"rows": {"start": index, "length": 1}} for index in range(n)]
    theta, theta_bytes = _ref([0.0] * (n * _D), [n, _D])
    sigma, sigma_bytes = _ref(_identity(n), [n, _D, _D])
    density, density_bytes = _ref([0.5] * n, [n])
    payload: dict[str, Any] = {
        "measurement_id": "ab" * 32,
        "frame_id": "frame-1",
        "input": {
            "kind": "window",
            "window_artifact_id": _WINDOW,
            "token_axis_artifact_id": _AXIS if axis else None,
        },
        "points": points,
        "theta": theta,
        "sigma": sigma,
        "density": density,
    }
    payload["measurement_id"] = _measurement_id(payload)
    parents = [
        {"role": "source_window", "ordered": False, "artifact_ids": [_WINDOW]},
    ]
    if axis:
        parents.append({"role": "token_axis", "ordered": False, "artifact_ids": [_AXIS]})
    envelope = {
        "kind": "interpretation",
        "payload_schema": {"id": "nvs.meaning-measurement", "version": "0.1.0"},
        "payload": payload,
        "producer": {"name": "meaning-mapper", "version": "2.3.0", "build": "mm"},
        "parents": parents,
    }
    window = {
        "artifact_id": _WINDOW,
        "payload_schema": {"id": "msr.trajectory-window", "version": "0.10.0"},
        "producer": {"name": "nvs-runtime", "version": "1.0.0", "build": "w"},
        "seq": 2,
        "parents": [
            {"role": "source_trajectory", "ordered": False, "artifact_ids": [_OBS]},
        ],
        "payload": {"window": {"length": length}, "origin": {"length": length}},
    }
    stored: dict[str, Any] = {_WINDOW: {"envelope": window}}
    blobs = {theta["uri"]: theta_bytes, sigma["uri"]: sigma_bytes, density["uri"]: density_bytes}
    if axis:
        stored[_AXIS] = {
            "envelope": {
                "artifact_id": _AXIS,
                "payload_schema": {"id": "nvs.token-temporal", "version": "0.1.0"},
                "producer": {"name": "sensos-inference", "version": "0.1.0", "build": "t"},
                "seq": 2,
                "parents": [
                    {"role": "source_observation", "ordered": False, "artifact_ids": [_OBS]},
                ],
                "payload": {"segments": [{"origin": "generated", "n": length}]},
            }
        }
    if observation:
        stored[_OBS] = {
            "envelope": {"artifact_id": _OBS, "payload": {"binding": {"alignment": alignment}}}
        }
    return envelope, stored, blobs


def _codes(
    envelope: dict[str, Any],
    stored: dict[str, Any],
    blobs: dict[str, bytes],
) -> list[str]:
    return [item.code for item in check_meaning_measurement(envelope, stored, blobs)]


def test_window_only_and_with_an_axis_are_clean() -> None:
    for n in (1, 3):
        for axis in (False, True):
            envelope, stored, blobs = _world(n, axis=axis)
            assert _codes(envelope, stored, blobs) == [], (n, axis)


def test_a_stored_observation_with_decides_next_is_clean() -> None:
    envelope, stored, blobs = _world(axis=True, observation=True)
    assert _codes(envelope, stored, blobs) == []


def test_a_small_asymmetry_within_the_spd_tolerance_is_clean() -> None:
    envelope, stored, blobs = _world()
    _replace(envelope["payload"], blobs, "sigma", [1.0, 1e-9, 0.0, 1.0], [1, _D, _D])
    assert _codes(envelope, stored, blobs) == []


def test_a_schema_failure_is_reported_alone() -> None:
    envelope, stored, blobs = _world()
    envelope["payload"]["extra"] = 1
    found = check_meaning_measurement(envelope, stored, blobs)
    assert [item.code for item in found] == ["schema"]
    assert found[0].message.startswith("payload/")


def test_each_tamper_emits_only_its_code() -> None:
    cases = {
        "producer": _tamper_producer,
        "parents": _tamper_parents,
        "input": _tamper_input,
        "input_axis": _tamper_input_axis,
        "parent_not_supplied": _tamper_missing_parent,
        "window": _tamper_window,
        "axis": _tamper_axis,
        "lineage": _tamper_lineage,
        "alignment": _tamper_alignment,
        "rows": _tamper_rows,
        "rows_n": _tamper_rows_n,
        "shape": _tamper_shape,
        "blob_not_supplied": _tamper_blob,
        "value": _tamper_value,
        "sigma": _tamper_sigma,
        "density": _tamper_density,
        "id": _tamper_id,
        "s34": _tamper_s34,
        "s25": _tamper_s25,
    }
    expected = {
        "producer": "meaning_measurement_producer",
        "parents": "meaning_measurement_parents",
        "input": "meaning_measurement_input",
        "input_axis": "meaning_measurement_input",
        "parent_not_supplied": "meaning_measurement_parent_not_supplied",
        "window": "meaning_measurement_window",
        "axis": "meaning_measurement_axis",
        "lineage": "meaning_measurement_lineage",
        "alignment": "meaning_measurement_alignment",
        "rows": "meaning_measurement_rows",
        "rows_n": "meaning_measurement_rows",
        "shape": "meaning_measurement_shape",
        "blob_not_supplied": "meaning_measurement_blob_not_supplied",
        "value": "meaning_measurement_value",
        "sigma": "meaning_measurement_sigma",
        "density": "meaning_measurement_density",
        "id": "meaning_measurement_id",
        "s34": "S34",
        "s25": "S25",
    }
    for name, mutate in cases.items():
        envelope, stored, blobs = _world(3, axis=True)
        mutate(envelope, stored, blobs)
        assert _codes(envelope, stored, blobs) == [expected[name]], name


def _tamper_producer(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del stored, blobs
    envelope["producer"]["name"] = "other"


def _tamper_parents(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del stored, blobs
    envelope["parents"][0]["ordered"] = True


def _tamper_input(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del stored, blobs
    envelope["payload"]["input"]["window_artifact_id"] = "art:" + "c" * 64
    envelope["payload"]["measurement_id"] = _measurement_id(envelope["payload"])


def _tamper_input_axis(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del stored, blobs
    envelope["payload"]["input"]["token_axis_artifact_id"] = None
    envelope["payload"]["measurement_id"] = _measurement_id(envelope["payload"])


def _tamper_missing_parent(
    envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]
) -> None:
    del envelope, blobs
    del stored[_WINDOW]


def _tamper_window(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del envelope, blobs
    stored[_WINDOW]["envelope"]["producer"]["name"] = "other"


def _tamper_axis(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del envelope, blobs
    stored[_AXIS]["envelope"]["payload_schema"]["version"] = "0.2.0"


def _tamper_lineage(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del envelope, blobs
    stored[_WINDOW]["envelope"]["parents"][0]["artifact_ids"] = ["art:" + "d" * 64]


def _tamper_alignment(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del envelope, blobs
    stored[_OBS] = {"envelope": {"payload": {"binding": {"alignment": "other"}}}}


def _tamper_rows(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del stored, blobs
    envelope["payload"]["points"][0]["rows"]["length"] = 99
    envelope["payload"]["measurement_id"] = _measurement_id(envelope["payload"])


def _tamper_rows_n(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del envelope, blobs
    stored[_WINDOW]["envelope"]["payload"]["origin"]["length"] = 99


def _tamper_shape(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del stored
    _replace(envelope["payload"], blobs, "theta", [0.0] * 9, [3, 3])


def _tamper_blob(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del envelope, stored
    del blobs[next(iter(blobs))]


def _tamper_value(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del stored
    _replace(envelope["payload"], blobs, "theta", [math.nan] * 6, [3, _D])


def _tamper_sigma(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del stored
    values = _identity(3)
    values[3] = -1.0
    _replace(envelope["payload"], blobs, "sigma", values, [3, _D, _D])


def _tamper_density(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del stored
    _replace(envelope["payload"], blobs, "density", [0.5, 1.5, 0.5], [3])


def _tamper_id(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del stored, blobs
    digest = envelope["payload"]["measurement_id"]
    envelope["payload"]["measurement_id"] = ("0" if digest[0] != "0" else "1") + digest[1:]


def _tamper_s34(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del stored
    ref = envelope["payload"]["theta"]
    data = blobs.pop(ref["uri"])
    flipped = ("0" if ref["sha256"][0] != "0" else "1") + ref["sha256"][1:]
    ref["uri"] = "blob:sha256:" + flipped
    blobs[ref["uri"]] = data


def _tamper_s25(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> None:
    del envelope, stored
    uri = next(iter(blobs))
    raw = bytearray(blobs[uri])
    raw[0] ^= 0x01
    blobs[uri] = bytes(raw)


def test_an_unknown_version_is_s39_and_0_1_0_reaches_the_check() -> None:
    envelope, stored, blobs = _world()
    assert check_nvs_payload(envelope, stored, blobs) == []
    other = copy.deepcopy(envelope)
    other["payload_schema"] = {"id": "nvs.meaning-measurement", "version": "0.2.0"}
    found = check_nvs_payload(other, stored, blobs)
    assert [(item.code, item.message) for item in found] == [
        ("S39", "unknown payload_schema nvs.meaning-measurement 0.2.0")
    ]
