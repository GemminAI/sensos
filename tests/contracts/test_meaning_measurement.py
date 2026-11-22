"""nvs.meaning-measurement 0.1.0: the payload checks, and the gate_nvs branch."""

from __future__ import annotations

import copy
import hashlib
import math
import struct
from typing import Any

from contracts.gate_nvs import check_nvs_payload
from contracts.hidden_trajectory import (
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_PASS_UNVERIFIED,
    Unverifiable,
)
from contracts.jcs import jcs
from contracts.meaning_measurement import check_meaning_measurement
from test_meaning_frame import _SPACE, _world as _frame_world

_OBS = "art:" + "1" * 64
_FRAME = "frame:sha256:" + "a" * 64
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
        "frame_id": _FRAME,
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


def _checked(
    envelope: dict[str, Any],
    stored: dict[str, Any],
    blobs: dict[str, bytes],
):
    return check_meaning_measurement(envelope, stored, blobs)


def _codes(
    envelope: dict[str, Any],
    stored: dict[str, Any],
    blobs: dict[str, bytes],
) -> list[str]:
    return [item.code for item in _checked(envelope, stored, blobs).violations]


def _assert_unverified(
    envelope: dict[str, Any],
    stored: dict[str, Any],
    blobs: dict[str, bytes],
) -> None:
    result = _checked(envelope, stored, blobs)
    assert result.status == STATUS_PASS_UNVERIFIED
    assert result.violations == ()
    assert result.unverifiable == (Unverifiable("frame_binding", "frame_not_supplied"),)


def test_window_only_and_with_an_axis_are_clean() -> None:
    for n in (1, 3):
        envelope, stored, blobs = _world(n, axis=False)
        _assert_unverified(envelope, stored, blobs)
        envelope, stored, blobs = _world(n, axis=True, observation=True)
        _assert_unverified(envelope, stored, blobs)


def test_an_axis_without_the_observation_is_refused() -> None:
    envelope, stored, blobs = _world(axis=True)
    assert _codes(envelope, stored, blobs) == ["meaning_measurement_observation_not_supplied"]


def test_an_axis_producer_that_is_not_sensos_inference_is_refused() -> None:
    envelope, stored, blobs = _world(axis=True, observation=True)
    stored[_AXIS]["envelope"]["producer"]["name"] = "nvs-runtime"
    assert _codes(envelope, stored, blobs) == ["meaning_measurement_axis"]


def test_a_stored_observation_with_decides_next_is_clean() -> None:
    envelope, stored, blobs = _world(axis=True, observation=True)
    _assert_unverified(envelope, stored, blobs)


def test_a_small_asymmetry_within_the_spd_tolerance_is_clean() -> None:
    envelope, stored, blobs = _world()
    _replace(envelope["payload"], blobs, "sigma", [1.0, 1e-9, 0.0, 1.0], [1, _D, _D])
    _assert_unverified(envelope, stored, blobs)


def test_a_frame_id_that_is_not_a_content_address_is_schema() -> None:
    for frame_id in (
        "f",
        "frame:sha256:" + "A" * 64,
        "frame:sha256:" + "a" * 63,
        "frame:sha256:" + "a" * 65,
        "id:sha256:" + "a" * 64,
    ):
        envelope, stored, blobs = _world()
        envelope["payload"]["frame_id"] = frame_id
        envelope["payload"]["measurement_id"] = _measurement_id(envelope["payload"])
        assert _codes(envelope, stored, blobs) == ["schema"], frame_id


def test_a_schema_failure_is_reported_alone() -> None:
    envelope, stored, blobs = _world()
    envelope["payload"]["extra"] = 1
    found = check_meaning_measurement(envelope, stored, blobs).violations
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
        envelope, stored, blobs = _world(3, axis=True, observation=True)
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
    reached = check_nvs_payload(envelope, stored, blobs)
    assert reached.status == STATUS_PASS_UNVERIFIED
    assert reached.violations == ()
    other = copy.deepcopy(envelope)
    other["payload_schema"] = {"id": "nvs.meaning-measurement", "version": "0.2.0"}
    found = check_nvs_payload(other, stored, blobs)
    assert [(item.code, item.message) for item in found.violations] == [
        ("S39", "unknown payload_schema nvs.meaning-measurement 0.2.0")
    ]


_FRAME_ART = "art:" + "e" * 64


def _install_frame(
    envelope: dict[str, Any],
    stored: dict[str, Any],
    blobs: dict[str, bytes],
    **kwargs: Any,
) -> dict[str, Any]:
    frame, frame_blobs = _frame_world(**kwargs)
    depth = frame["payload"]["D"]
    envelope["payload"]["frame_id"] = frame["payload"]["frame_id"]
    envelope["payload"]["measurement_id"] = _measurement_id(envelope["payload"])
    stored[_FRAME_ART] = {"envelope": frame}
    blobs.update(frame_blobs)
    stored[_WINDOW]["envelope"]["payload"]["dimension"] = depth
    return frame


def _observe(
    stored: dict[str, Any],
    *,
    space: str = _SPACE,
    dimension: int = 3,
) -> None:
    stored[_OBS] = {
        "envelope": {
            "artifact_id": _OBS,
            "space_id": space,
            "payload": {"dimension": dimension, "binding": {"alignment": "decides-next/1"}},
        }
    }


def test_a_frame_and_its_observation_pass() -> None:
    envelope, stored, blobs = _world()
    _install_frame(envelope, stored, blobs)
    _observe(stored)
    result = _checked(envelope, stored, blobs)
    assert result.status == STATUS_PASS
    assert result.violations == ()
    assert result.unverifiable == ()


def test_a_missing_frame_is_unverified_and_a_bad_frame_is_a_failure() -> None:
    missing, stored, blobs = _world()
    unverified = _checked(missing, stored, blobs)
    assert unverified.status == STATUS_PASS_UNVERIFIED
    assert unverified.violations == ()
    assert unverified.unverifiable == (Unverifiable("frame_binding", "frame_not_supplied"),)

    refused, stored, blobs = _world()
    _install_frame(refused, stored, blobs, sigma0=[1.0, 0.0, 0.0, -1.0])
    _observe(stored)
    failed = _checked(refused, stored, blobs)
    assert failed.status == STATUS_FAIL
    assert failed.unverifiable == ()
    assert [item.code for item in failed.violations] == ["meaning_measurement_frame_invalid"]
    assert "meaning_frame_sigma0" in failed.violations[0].message


def test_a_missing_observation_is_unverified_when_the_frame_is_present() -> None:
    envelope, stored, blobs = _world()
    _install_frame(envelope, stored, blobs)
    result = _checked(envelope, stored, blobs)
    assert result.status == STATUS_PASS_UNVERIFIED
    assert result.violations == ()
    assert result.unverifiable == (Unverifiable("frame_space", "observation_not_supplied"),)


def test_a_different_space_id_is_refused() -> None:
    envelope, stored, blobs = _world()
    _install_frame(envelope, stored, blobs)
    _observe(stored, space="hid:" + "cd" * 32)
    assert _codes(envelope, stored, blobs) == ["meaning_measurement_frame_space"]


def test_a_window_dimension_that_differs_from_frame_d_is_refused() -> None:
    envelope, stored, blobs = _world()
    _install_frame(envelope, stored, blobs)
    _observe(stored)
    stored[_WINDOW]["envelope"]["payload"]["dimension"] = 9
    assert _codes(envelope, stored, blobs) == ["meaning_measurement_frame_dimension"]


def test_an_observation_dimension_that_differs_from_frame_d_is_refused() -> None:
    envelope, stored, blobs = _world()
    _install_frame(envelope, stored, blobs)
    _observe(stored, dimension=9)
    assert _codes(envelope, stored, blobs) == ["meaning_measurement_frame_dimension"]


def test_a_frame_rank_that_differs_from_theta_is_refused() -> None:
    envelope, stored, blobs = _world()
    identity = [1.0 if row == col else 0.0 for row in range(3) for col in range(3)]
    _install_frame(
        envelope,
        stored,
        blobs,
        d=3,
        depth=3,
        mu=[1.0, 2.0, 3.0],
        basis=identity,
        sigma0=identity,
    )
    _observe(stored)
    assert _codes(envelope, stored, blobs) == ["meaning_measurement_frame_dimension"]


def test_a_stage1_violation_fails_with_or_without_a_frame() -> None:
    without, stored, blobs = _world()
    without["producer"]["name"] = "other"
    refused = _checked(without, stored, blobs)
    assert refused.status == STATUS_FAIL
    assert _codes(without, stored, blobs) == ["meaning_measurement_producer"]

    with_frame, stored, blobs = _world()
    _install_frame(with_frame, stored, blobs)
    _observe(stored)
    with_frame["producer"]["name"] = "other"
    refused = _checked(with_frame, stored, blobs)
    assert refused.status == STATUS_FAIL
    assert _codes(with_frame, stored, blobs) == ["meaning_measurement_producer"]
