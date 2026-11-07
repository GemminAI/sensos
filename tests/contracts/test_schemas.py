"""Schema validity, lint rules from design 0.7.1 (section 2.1/7), the lock, and a
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


# The only integer without bounds: msr/calibration 0.8.0 ``exponent``. Its range is not decided yet
# (Tomo 11-07 15:29: decided later in the contract design); the Gate checks presence and form only.
UNBOUNDED_BY_DECISION = {("msr/calibration.schema.json", "/properties/exponent")}


@pytest.mark.parametrize("rel", SCHEMA_PATHS)
def test_every_integer_has_bounds(rel: str) -> None:
    for path, node in _walk(load_schema(rel)):
        if "integer" in _types(node) and (rel, path) not in UNBOUNDED_BY_DECISION:
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
    assert schema["$id"].endswith("/1.0.0")
    assert props["contract"]["properties"]["id"] == {"const": "IC-00"}
    assert props["contract"]["properties"]["version"] == {"const": "1.0.0"}
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
    assert lock["contract_id"] == "IC-00" and lock["version"] == "1.0.0"
    recorded = {e["path"]: e["sha256"] for e in lock["schemas"]}
    assert sorted(recorded) == sorted(SCHEMA_PATHS)
    for rel, digest in recorded.items():
        assert hashlib.sha256((CONTRACTS_DIR / rel).read_bytes()).hexdigest() == digest, rel
    for entry in lock["schemas"] + lock["archived"]:
        schema = load_schema(entry["path"])
        assert schema["$id"] == entry["id"]
        if entry["path"].startswith("common/") and entry["path"] != "common/blob.schema.json":
            assert entry["id"].endswith("/1.0.0")
    archived = {e["path"]: e["sha256"] for e in lock["archived"]}
    assert archived == {
        "msr/archive/0.6.1/calibration.schema.json": "47e5bc48e736f774b21a5f61b400ab203bd776cc0db0538024a35fd32cc24d58",
        "msr/archive/0.7.0/calibration.schema.json": "7a702f1ff8305ed808885a46b9b200d75380f66fd45276888867ad1eb93d8c72",
        "msr/archive/0.6.2/geometry-measurement.schema.json": "b5e96c646d3937123e00398f6a479f6823e0f551e5dc6e37f095d92d8d513ca4",
        "msr/archive/0.7.0/geometry-measurement.schema.json": "ce96a21095fae83603b73eb0933a7605535455eb335c20fdd0882178e8c1339a",
        "msr/archive/0.8.0/geometry-measurement.schema.json": "d9aa7ea59237c4c6f19d33bbac6506ce0983b10ce46a3ee3a94b076b9bd05f6e",
    }
    for rel, digest in archived.items():
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
QUANT = {"quantum": {"base": 2, "exponent": -30}, "rounding": "ties-to-even", "tolerance_quanta": 1}
SERIES_UNITS = {
    "displacement_mean": ("distance", True),
    "displacement_median": ("distance", True),
    "displacement_longest_sub_delta_run": ("steps", False),
    "recurrence_pair_fraction": ("fraction", True),
    "recurrence_return_count": ("returns", False),
    "recurrence_return_rate": ("returns_per_point", True),
    "diversity_cell_entropy": ("nats", True),
    "diversity_participation_ratio": ("dimensionless", True),
    "persistence_longest_stay": ("points", False),
    "persistence_dominant_cell_share": ("fraction", True),
}


def _series(length: int = 10) -> dict[str, Any]:
    return {
        name: {
            "uri": "blob:sha256:" + H64,
            "sha256": H64,
            "media_type": "application/vnd.sensos.ndarray-raw",
            "dtype": "int64",
            "shape": [length],
            "byte_order": "little",
            "order": "C",
            "unit": unit,
            "quantization": copy.deepcopy(QUANT) if real else None,
            "undefined": "int64_min",
        }
        for name, (unit, real) in SERIES_UNITS.items()
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
        "series": _series(),
        "verdict": {"state": None, "reason": "shift verdict applies to trajectory pairs (SPEC-MSR-001 v2 §3.2)"},
    }


def _errors(sample: dict[str, Any]) -> list[Any]:
    # these samples are the 0.7.1 shape (no input_scope): the IC-02 0.8.0 rule, kept in the archive
    return list(validator("msr/archive/0.8.0/geometry-measurement.schema.json").iter_errors(sample))


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
    first = "displacement_mean"
    single("series-dtype-removed", lambda s: s["series"][first].pop("dtype"))
    single("series-big-endian", lambda s: s["series"][first].update(byte_order="big"))
    single("series-rounding-changed", lambda s: s["series"][first]["quantization"].update(rounding="half-up"))
    single("series-float-blob", lambda s: s["series"][first].update(dtype="float64"))
    single("series-name-missing", lambda s: s["series"].pop("recurrence_return_rate"))
    single("series-extra-name", lambda s: s["series"].update(extra=copy.deepcopy(s["series"][first])))
    single("series-as-one-blob", lambda s: s.update(series=s["series"][first]))
    single("series-two-dimensional", lambda s: s["series"][first].update(shape=[2, 5]))
    single("series-empty-shape-element", lambda s: s["series"][first].update(shape=[0]))
    single("series-real-without-quantization", lambda s: s["series"][first].update(quantization=None))
    single("series-count-with-quantization", lambda s: s["series"]["recurrence_return_count"].update(quantization=copy.deepcopy(QUANT)))
    single("series-real-wrong-exponent", lambda s: s["series"][first]["quantization"]["quantum"].update(exponent=-20))
    single("series-wrong-unit", lambda s: s["series"][first].update(unit="nats"))
    single("series-uri-not-blob", lambda s: s["series"][first].update(uri="file:///x"))
    single("series-bad-undefined", lambda s: s["series"][first].update(undefined="zero"))
    single("mode-unknown", lambda s: s.update(mode="triple"))
    return out


MUTATIONS = _mutations()


@pytest.mark.parametrize(("name", "sample"), MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_msr_measurement_rejections(name: str, sample: dict[str, Any]) -> None:
    assert _errors(sample), f"{name} should be rejected"


def test_msr_series_must_always_declare_undefined() -> None:
    single = _single()
    assert all(r["undefined"] == "int64_min" for r in single["series"].values())
    assert _errors(single) == []
    for name in single["series"]:
        broken = _single()
        del broken["series"][name]["undefined"]
        assert _errors(broken), f"{name}: declaration is required in 0.7.1"
    other = _single()
    other["series"]["displacement_mean"]["undefined"] = "zero"
    assert _errors(other)


def test_archived_0_6_schemas_still_accept_their_old_samples() -> None:
    old = validator("msr/archive/0.6.2/geometry-measurement.schema.json")
    assert not list(old.iter_errors(PAIR))
    one = _single()
    one["series"] = {
        "uri": "blob://series/1",
        "sha256": H64,
        "media_type": "application/vnd.sensos.ndarray-raw",
        "dtype": "int64",
        "shape": [10, 10],
        "byte_order": "little",
        "order": "C",
        "unit": "msr-geometry-series/1",
        "quantization": copy.deepcopy(QUANT),
    }
    assert not list(old.iter_errors(one))
    assert _errors(one), "the 0.7.1 schema rejects the 0.6.2 single-Blob series"
    v070 = validator("msr/archive/0.7.0/geometry-measurement.schema.json")
    two = _single()
    for ref in two["series"].values():
        del ref["undefined"]  # 0.7.0 allowed omitting it
    assert not list(v070.iter_errors(two))
    assert _errors(two), "0.7.1 requires the declaration"
    cal = validator("msr/archive/0.6.1/calibration.schema.json")
    assert not list(cal.iter_errors(_cal()))


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


def _cal080() -> dict[str, Any]:
    return {"exponent": -30, **_cal()}


def test_msr_calibration_070_is_archived_with_its_own_rule() -> None:
    old = validator("msr/archive/0.7.0/calibration.schema.json")
    assert [e.message for e in old.iter_errors(_cal())] == []
    assert list(old.iter_errors(_cal080())), "0.7.0 has no exponent field"
    new = validator("msr/calibration.schema.json")
    assert list(new.iter_errors(_cal())), "a 0.7.0 payload is never read as 0.8.0"


def test_msr_calibration_exponent_is_declared_not_fixed() -> None:
    schema = load_schema("msr/calibration.schema.json")
    assert schema["$id"].endswith("/0.8.0") and "exponent" in schema["required"]
    assert schema["properties"]["exponent"]["type"] == "integer"
    assert not {"minimum", "maximum", "const", "enum"} & set(schema["properties"]["exponent"])  # no range in 0.8.0
    for name, node in schema["properties"]["values"]["properties"].items():
        quantum = node.get("x-sensos-quantization", {}).get("quantum")
        if quantum is not None:
            assert quantum == {"base": 2, "exponent_from": "/exponent"}, name  # not -30
    v = validator("msr/calibration.schema.json")
    assert [e.message for e in v.iter_errors({**_cal080(), "exponent": -20})] == []


def test_msr_calibration_samples() -> None:
    v = validator("msr/calibration.schema.json")
    sample = _cal080()
    assert [e.message for e in v.iter_errors(sample)] == []
    bad_cases = []
    for name, fn in (
        ("float-epsilon", lambda s: s["values"].update(epsilon=0.5)),
        ("missing-null-set", lambda s: s.pop("null_set")),
        ("duplicate-null-set", lambda s: s.update(null_set=[s["null_set"][0]] * 2)),
        ("wrong-method-name", lambda s: s["method"].update(name="other")),
        ("extra-field", lambda s: s.update(file_sha256=H64)),
        ("negative-w-min", lambda s: s["values"].update(w_min=-1)),
        ("missing-exponent", lambda s: s.pop("exponent")),
        ("string-exponent", lambda s: s.update(exponent="-30")),
        ("bool-exponent", lambda s: s.update(exponent=True)),
        ("null-exponent", lambda s: s.update(exponent=None)),
        ("fraction-exponent", lambda s: s.update(exponent=-20.5)),
    ):
        s = copy.deepcopy(sample)
        fn(s)
        bad_cases.append((name, s))
    failed = [name for name, s in bad_cases if not list(v.iter_errors(s))]
    assert failed == [], f"accepted but should fail: {failed}"
