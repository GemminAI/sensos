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
    "msr/calibration.schema.json",
    "msr/geometry-measurement.schema.json",
)


def load_schema(relpath: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((CONTRACTS_DIR / relpath).read_text(encoding="utf-8"))
    return data


def registry() -> Registry[Any]:
    reg: Registry[Any] = Registry()
    for rel in SCHEMA_PATHS:
        schema = load_schema(rel)
        reg = reg.with_resource(schema["$id"], Resource.from_contents(schema, DRAFT202012))
    return reg


def validator(relpath: str) -> Draft202012Validator:
    schema = load_schema(relpath)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=registry())
