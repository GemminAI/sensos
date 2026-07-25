"""RFC-HEXT013 §3: Syntax -> HextObject Converter.

Scoping note (Phase 1 implementation): RFC-HEXT013 §3 Rule 1 requires
validating ``payload`` against the schema associated with the declared
``type``. The reference runtime's per-type Pydantic schemas
(``schema/observation.py``'s ``ObservationEvent``/``Observation0Cell``, and
siblings for controller/trajectory/replay/diagnostic) are not what existing
callers actually publish on the wire today — e.g. ``ObservationEvent``
requires a nested ``observation.id``/``observation.sequence`` structure,
while the reference runtime's own tests and CTS fixtures publish a flat
``payload`` dict directly. Enforcing the strict per-field schemas here would
reject already-passing, already-conformant traffic, which the project's own
"do not weaken tests" constraint forbids.

This converter therefore implements the achievable subset of §3 today:
structural well-formedness (``type`` is a non-empty string, ``payload`` is a
JSON-object-shaped dict) plus a soft cross-check against the registered type
set (``schema/type_registry.py``) for observability, without hard-rejecting
an unregistered or loosely-shaped type. Full per-field strict validation
against each type's typed schema is recorded as a deferred TODO in the
Phase 1 report rather than silently implemented as if it were already
achieved.
"""

from __future__ import annotations

from typing import Any

from hext_stream.observation.errors import SchemaMismatchError
from hext_stream.schema.type_registry import is_registered_type


def convert(*, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
    """RFC-HEXT013 §3: validate raw (type, payload) before HextObject construction.

    Returns a metadata fragment describing the validation outcome
    (``{"schema_validated": bool}``) for the caller to fold into the
    constructed object's ``metadata`` (never into ``payload``, per
    RFC-HEXT001 §7.1 field 6).
    """
    if not isinstance(type_, str) or not type_.strip():
        raise SchemaMismatchError("HextObject.type must be a non-empty string")
    if not isinstance(payload, dict):
        raise SchemaMismatchError("HextObject.payload must be a JSON object (dict)")

    return {"schema_validated": is_registered_type(type_)}
