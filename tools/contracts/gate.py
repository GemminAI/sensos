"""Gate steps beyond IC-00 itself (design v0.7.1 section 5, steps 1 and 8).

``check_envelope`` (frozen IC-00 scope) is unchanged; this module adds the
payload side: S39 (known ``payload_schema`` ``{id, version}``), the payload's
schema, and the IC-02 checks. Unknown versions are rejected, never guessed.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator

from contracts.check import Violation
from contracts.ic02 import check_geometry
from contracts.schemas import validator

# (payload_schema.id, payload_schema.version) -> schema path. The version is the
# version in the schema's $id (design 2.6); it is not IC-00's contract.version.
PAYLOAD_SCHEMAS: dict[tuple[str, str], str] = {
    ("msr.geometry-measurement", "0.7.0"): "msr/geometry-measurement.schema.json",
    ("msr.calibration", "0.7.0"): "msr/calibration.schema.json",
}


@cache
def _validator(path: str) -> Draft202012Validator:
    return validator(path)


def check_payload(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any] | None = None,
    blobs: Mapping[str, bytes] | None = None,
) -> list[Violation]:
    declared = envelope["payload_schema"]
    path = PAYLOAD_SCHEMAS.get((declared["id"], declared["version"]))
    if path is None:
        return [Violation("S39", f"unknown payload_schema {declared['id']} {declared['version']}")]
    errors = sorted(_validator(path).iter_errors(envelope["payload"]), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        return [Violation("schema", f"payload/{'/'.join(str(p) for p in first.absolute_path)}: {first.message}")]
    if declared["id"] == "msr.geometry-measurement":
        return check_geometry(envelope, stored or {}, blobs or {})
    return []
