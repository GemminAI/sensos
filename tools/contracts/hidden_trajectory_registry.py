"""Schema registry for nvs.hidden-trajectory 0.1.0 (U5-3).

``schemas.py`` is pinned by the IC-02 0.10.0 lock, so the schemas of this contract are added here instead:
``hidden_trajectory_registry()`` is ``contracts.schemas.registry()`` plus the payload schema and the float32
Blob it ``$ref``s, and ``hidden_trajectory_validator`` is ``contracts.schemas.validator`` over that registry.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from contracts.schemas import load_schema, registry

HIDDEN_TRAJECTORY_PATHS = (
    "common/float32-blob.schema.json",
    "nvs/hidden-trajectory.schema.json",
)


def hidden_trajectory_registry() -> Registry[Any]:
    reg = registry()
    for rel in HIDDEN_TRAJECTORY_PATHS:
        schema = load_schema(rel)
        reg = reg.with_resource(
            schema["$id"], Resource.from_contents(schema, DRAFT202012)
        )
    return reg


def hidden_trajectory_validator(relpath: str) -> Draft202012Validator:
    schema = load_schema(relpath)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=hidden_trajectory_registry())
