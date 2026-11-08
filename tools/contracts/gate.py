"""Gate steps beyond IC-00 itself (design v0.7.1 section 5, steps 1 and 8).

``check_envelope`` (frozen IC-00 scope) is unchanged; this module adds the
payload side (the complete schema check belongs to the Gate, before storing; a
reader still recomputes ids and checks the fields it uses, the contract version
and the parents' consistency): S39 (known ``payload_schema`` ``{id, version}``), the payload's
schema, and the IC-02 checks. Unknown versions are rejected, never guessed.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator

from contracts.check import Violation
from contracts.ic02 import check_calibration_parents, check_geometry
from contracts.ic02_window import check_scope, check_window
from contracts.schemas import validator

# (payload_schema.id, payload_schema.version) -> schema path. The version is the
# version in the schema's $id (design 2.6); it is not IC-00's contract.version.
PAYLOAD_SCHEMAS: dict[tuple[str, str], str] = {
    ("msr.geometry-measurement", "0.9.0"): "msr/geometry-measurement.schema.json",
    # IC-02 0.8.0 rule, unchanged (no ``input_scope``). A 0.7.1 payload is read by this schema and the
    # same ``check_geometry``; it is never read as 0.9.0 and never asked for a window.
    ("msr.geometry-measurement", "0.7.1"): "msr/archive/0.8.0/geometry-measurement.schema.json",
    ("msr.trajectory-window", "0.9.0"): "msr/trajectory-window.schema.json",
    ("msr.calibration", "0.8.0"): "msr/calibration.schema.json",
    # old rule, unchanged (no ``exponent`` field, fixed at -30). Never interpreted as 0.8.0;
    # how old data moves to 0.8.0 is a separate decision and is not implemented here.
    ("msr.calibration", "0.7.0"): "msr/archive/0.7.0/calibration.schema.json",
}


_MISSING = object()


@cache
def _validator(path: str) -> Draft202012Validator:
    return validator(path)


def check_payload(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any] | None = None,
    blobs: Mapping[str, bytes] | None = None,
    parent_contents: Mapping[str, str] | None = None,
) -> list[Violation]:
    declared = envelope["payload_schema"]
    path = PAYLOAD_SCHEMAS.get((declared["id"], declared["version"]))
    if path is None:
        return [Violation("S39", f"unknown payload_schema {declared['id']} {declared['version']}")]
    if (declared["id"], declared["version"]) == ("msr.calibration", "0.8.0"):
        # 0.8.0: ``exponent`` is required and a JSON integer (presence and form only, no range).
        # The schema alone would let a float such as -20.0 through.
        exponent = envelope["payload"].get("exponent", _MISSING) if isinstance(envelope["payload"], Mapping) else _MISSING
        if type(exponent) is not int:
            why = "missing" if exponent is _MISSING else f"must be an integer, not {type(exponent).__name__}"
            return [Violation("schema", f"payload/exponent: {why}")]
    errors = sorted(_validator(path).iter_errors(envelope["payload"]), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        return [Violation("schema", f"payload/{'/'.join(str(p) for p in first.absolute_path)}: {first.message}")]
    if declared["id"] == "msr.trajectory-window":
        return check_window(envelope, stored or {}, blobs or {})
    if declared["id"] == "msr.geometry-measurement":
        found = check_geometry(envelope, stored or {}, blobs or {})
        if declared["version"] == "0.9.0" and envelope["payload"]["mode"] == "single":
            found += check_scope(envelope, stored or {})
        return found
    if declared["id"] == "msr.calibration" and parent_contents is not None:
        return check_calibration_parents(envelope, parent_contents)
    return []
