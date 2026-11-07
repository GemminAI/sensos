"""Loading the contract schemas (common/ and msr/) with cross-file $ref support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "architecture" / "contracts"
SCHEMA_PATHS = (
    "common/artifact.schema.json",
    "common/provenance.schema.json",
    "common/uncertainty.schema.json",
    "common/blob.schema.json",
    "msr/calibration.schema.json",
    "msr/geometry-measurement.schema.json",
)
# IC-02 0.9.0 additions (D-129). Kept apart from SCHEMA_PATHS so the schemas the IC-02 0.8.0 tests are
# parametrized over keep their number; tests/contracts/test_ic02_window.py applies the same lint to these.
IC02_V090_PATHS = ("msr/trajectory-window.schema.json",)
# Kept for the record (design Appendix A); self-contained. Only the 0.7.0 calibration
# is still read by the Gate (its own rule, exponent fixed at -30; never read as 0.8.0).
ARCHIVED_PATHS = (
    "msr/archive/0.6.1/calibration.schema.json",
    "msr/archive/0.7.0/calibration.schema.json",
    "msr/archive/0.6.2/geometry-measurement.schema.json",
    "msr/archive/0.7.0/geometry-measurement.schema.json",
    "msr/archive/0.8.0/geometry-measurement.schema.json",
)


def load_schema(relpath: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((CONTRACTS_DIR / relpath).read_text(encoding="utf-8"))
    return data


def registry() -> Registry[Any]:
    reg: Registry[Any] = Registry()
    for rel in (*SCHEMA_PATHS, *IC02_V090_PATHS, *ARCHIVED_PATHS):
        schema = load_schema(rel)
        reg = reg.with_resource(schema["$id"], Resource.from_contents(schema, DRAFT202012))
    return reg


def validator(relpath: str) -> Draft202012Validator:
    schema = load_schema(relpath)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=registry())
