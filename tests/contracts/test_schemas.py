"""Schema validity, lint rules from design 0.6.2 (section 2.1/7), the lock, and a
minimal pass/fail sample set for the two copied msr schemas."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from contracts.schemas import CONTRACTS_DIR, SCHEMA_PATHS, load_schema, validator
from jsonschema import Draft202012Validator

LOCK = Path(__file__).with_name("contract.lock")
H64 = "a" * 64


def _walk(node: Any, path: str = "") -> Any:
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from _walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, f"{path}/{i}")


def _types(schema: dict[str, Any]) -> list[str]:
    t = schema.get("type")
    return [t] if isinstance(t, str) else list(t) if isinstance(t, list) else []


@pytest.mark.parametrize("rel", SCHEMA_PATHS)
def test_schema_is_valid_draft_2020_12(rel: str) -> None:
    schema = load_schema(rel)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.parametrize("rel", SCHEMA_PATHS)
def test_every_integer_has_bounds(rel: str) -> None:
    for path, node in _walk(load_schema(rel)):
        if "integer" in _types(node):
            lo = "minimum" in node or "exclusiveMinimum" in node
            hi = "maximum" in node or "exclusiveMaximum" in node
            assert lo and hi, f"{rel}{path}: integer without min/max"


@pytest.mark.parametrize("rel", SCHEMA_PATHS)
def test_every_array_declares_order(rel: str) -> None:
    for path, node in _walk(load_schema(rel)):
        if "array" in _types(node):
            assert isinstance(node.get("x-sensos-ordered"), bool), f"{rel}{path}: missing x-sensos-ordered"
            if node["x-sensos-ordered"] is False:
                assert node.get("x-sensos-sort-key"), f"{rel}{path}: unordered array without sort key"


def test_envelope_id_patterns_and_constants() -> None:
    schema = load_schema("common/artifact.schema.json")
    props = schema["properties"]
    assert schema["$id"].endswith("/0.6.2")
    assert props["contract"]["properties"]["id"] == {"const": "IC-00"}
    assert props["contract"]["properties"]["version"] == {"const": "0.6.2"}
    assert props["content_id"]["pattern"] == "^cnt:[0-9a-f]{64}$"
    assert props["artifact_id"]["pattern"] == "^art:[0-9a-f]{64}$"
    assert set(props["kind"]["enum"]) == {"observation", "evidence", "interpretation", "selection", "outcome"}
    assert props["extensions"]["propertyNames"] == {"pattern": "^x-"}
    assert schema["unevaluatedProperties"] is False


def test_uncertainty_requires_method() -> None:
    v = validator("common/uncertainty.schema.json")
    ok = {"value": 3, "method": "msr-null-quantile", "meaning": "spread", "scale": {"base": 2, "exponent": -30}}
    assert not list(v.iter_errors(ok))
    for drop in ("method", "value", "meaning", "scale"):
        bad = {k: x for k, x in ok.items() if k != drop}
        assert list(v.iter_errors(bad)), drop
    assert list(v.iter_errors({**ok, "method": ""}))
    assert list(v.iter_errors({**ok, "value": 1.5}))


def test_lock_matches_files() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert lock["contract_id"] == "IC-00" and lock["version"] == "0.6.2"
    recorded = {e["path"]: e["sha256"] for e in lock["schemas"]}
    assert sorted(recorded) == sorted(SCHEMA_PATHS)
    for rel, digest in recorded.items():
        assert hashlib.sha256((CONTRACTS_DIR / rel).read_bytes()).hexdigest() == digest, rel


# ----------------------------------------------------- msr schema samples

CAL = {"artifact_id": "art:" + "1" * 64, "content_id": "cnt:" + "2" * 64}
INPUT_REF = {
    "sha256": H64,
    "model_build_id": "m1",
    "policy": {"name": "last-token", "sha256": H64},
    "length": 10,
    "dimension": 4,
}
SERIES = {
    "uri": "blob://series/1",
    "sha256": H64,
    "media_type": "application/vnd.sensos.ndarray-raw",
    "dtype": "int64",
    "shape": [10],
    "byte_order": "little",
    "order": "C",
    "unit": "distance",
    "quantization": {"quantum": {"base": 2, "exponent": -30}, "rounding": "ties-to-even", "tolerance_quanta": 1},
}
PAIR = {
    "mode": "pair",
    "space_id": "S1",
    "inputs": {"left": INPUT_REF, "right": INPUT_REF},
    "calibration": CAL,
    "alignment": {"mode": "equal_only", "points_used": 10},
    "distance": {"definition": "mean_step_l2", "value": 5 << 30},
    "verdict": {"state": "NOISE_FLOOR_INTERNAL"},
}


def _single() -> dict[str, Any]:
    return {
        "mode": "single",
        "space_id": "S1",
        "source": "T-hid",
        "layer": 12,
        "input_ref": INPUT_REF,
        "calibration": CAL,
        "thresholds": {
            "epsilon": 1 << 28,
            "delta": 1 << 20,
            "w_min": 1,
            "source": {"epsilon": "calibration", "delta": "calibration", "w_min": "calibration"},
        },
        "metrics": {
            "displacement": {"count": 9, "mean": 1 << 29, "median": 1 << 29, "longest_sub_delta_run": 2},
            "recurrence": {"pair_fraction": 1 << 20, "return_count": 1, "return_rate": 1 << 25},
            "diversity": {"cell_entropy": 1 << 29, "participation_ratio": 1 << 30},
            "persistence": {"longest_stay": 3, "dominant_cell_share": 1 << 29},
        },
        "series": copy.deepcopy(SERIES),
        "verdict": {"state": None, "reason": "shift verdict applies to trajectory pairs (SPEC-MSR-001 v2 §3.2)"},
    }


def _errors(sample: dict[str, Any]) -> list[Any]:
    return list(validator("msr/geometry-measurement.schema.json").iter_errors(sample))


def test_msr_pair_and_single_samples_pass() -> None:
    assert _errors(PAIR) == []
    single = _single()
    assert _errors(single) == [], [e.message for e in _errors(single)][:3]


def _mutations() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []

    def pair(name: str, fn: Any) -> None:
        s = copy.deepcopy(PAIR)
        fn(s)
        out.append((name, s))

    pair("float-distance", lambda s: s["distance"].update(value=1.5))
    pair("negative-distance", lambda s: s["distance"].update(value=-1))
    pair("distance-above-int-range", lambda s: s["distance"].update(value=2**53))
    pair("bad-verdict-state", lambda s: s["verdict"].update(state="MAYBE"))
    pair("uncalibrated-null-calibration-with-shift-state", lambda s: s.update(calibration=None))
    pair("unknown-alignment-mode", lambda s: s["alignment"].update(mode="common_prefix"))
    pair("points-used-zero", lambda s: s["alignment"].update(points_used=0))
    pair("extra-field", lambda s: s.update(extra=1))
    pair("missing-inputs", lambda s: s.pop("inputs"))
    pair("wrong-definition", lambda s: s["distance"].update(definition="l2"))
    pair("bad-calibration-id", lambda s: s["calibration"].update(artifact_id="art:xyz"))
    pair("empty-space-id", lambda s: s.update(space_id=""))

    def single(name: str, fn: Any) -> None:
        s = _single()
        fn(s)
        out.append((name, s))

    single("single-with-verdict-state", lambda s: s["verdict"].update(state="STAGNANT"))
    single("single-verdict-reason-changed", lambda s: s["verdict"].update(reason="x"))
    single("calibration-source-without-calibration", lambda s: s.update(calibration=None))
    single("float-epsilon", lambda s: s["thresholds"].update(epsilon=0.5))
    single("return-rate-above-one", lambda s: s["metrics"]["recurrence"].update(return_rate=(1 << 30) + 1))
    single("bad-source", lambda s: s.update(source="T-x"))
    single("blob-dtype-removed", lambda s: s["series"].pop("dtype"))
    single("blob-big-endian", lambda s: s["series"].update(byte_order="big"))
    single("blob-rounding-changed", lambda s: s["series"]["quantization"].update(rounding="half-up"))
    single("blob-media-type-changed", lambda s: s["series"].update(media_type="application/octet-stream"))
    single("blob-float-without-comparison", lambda s: s["series"].update(dtype="float64"))
    single("mode-unknown", lambda s: s.update(mode="triple"))
    return out


MUTATIONS = _mutations()


@pytest.mark.parametrize(("name", "sample"), MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_msr_measurement_rejections(name: str, sample: dict[str, Any]) -> None:
    assert _errors(sample), f"{name} should be rejected"


def test_msr_float_blob_with_comparison_passes() -> None:
    single = _single()
    blob = single["series"]
    blob.pop("quantization")
    blob.update(dtype="float64", comparison={"rule": "absolute_error", "bound": {"base": 2, "exponent": -30}})
    assert _errors(single) == [], [e.message for e in _errors(single)][:3]


def _cal() -> dict[str, Any]:
    return {
        "space_id": "S1",
        "model_build_id": "m1",
        "method": {
            "name": "msr-geometry-calibration",
            "version": "msr-geometry-calibration/1",
            "quantiles": {"epsilon": 1 << 25, "delta": 1 << 26, "floor": [1 << 25, (1 << 30) - (1 << 25)]},
        },
        "null_set": [f"art:{i:064x}" for i in range(2)],
        "between_alignment": "equal_only",
        "values": {
            "noise_floor_lower": 1 << 30,
            "noise_floor_upper": 2 << 30,
            "background_mean": 3 << 29,
            "epsilon": 1 << 28,
            "delta": 1 << 20,
            "w_min": 1,
            "codebook_ref": None,
        },
        "sample_config": {"trajectories": 2, "points": 40, "dims": 3},
    }


def test_msr_calibration_samples() -> None:
    v = validator("msr/calibration.schema.json")
    sample = _cal()
    assert [e.message for e in v.iter_errors(sample)] == []
    bad_cases = []
    for name, fn in (
        ("float-epsilon", lambda s: s["values"].update(epsilon=0.5)),
        ("missing-null-set", lambda s: s.pop("null_set")),
        ("duplicate-null-set", lambda s: s.update(null_set=[s["null_set"][0]] * 2)),
        ("wrong-method-name", lambda s: s["method"].update(name="other")),
        ("extra-field", lambda s: s.update(file_sha256=H64)),
        ("negative-w-min", lambda s: s["values"].update(w_min=-1)),
    ):
        s = copy.deepcopy(sample)
        fn(s)
        bad_cases.append((name, s))
    failed = [name for name, s in bad_cases if not list(v.iter_errors(s))]
    assert failed == [], f"accepted but should fail: {failed}"
