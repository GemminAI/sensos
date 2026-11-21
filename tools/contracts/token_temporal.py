"""Gate checks for ``nvs.token-temporal`` 0.1.0 (design §7).

The return is ``list[Violation]``, the same type as ``ic02_window.check_window``. A schema
failure is reported alone. After that, every failure that is found is returned. There is no
UNVERIFIABLE row: a missing ID-list Blob is ``token_temporal_blob_not_supplied``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Resource
from referencing.jsonschema import DRAFT202012

from contracts.blob import check_blob
from contracts.check import Violation
from contracts.jcs import jcs
from contracts.schemas import load_schema, registry

SCHEMA_PATH = "nvs/token-temporal.schema.json"
KIND = "observation"
PRODUCER = "sensos-inference"
PARENT_ROLE = "source_observation"
PARENT_SCHEMA_ID = "nvs.hidden-trajectory"
PARENT_SCHEMA_VERSION = "0.1.0"
SEGMENT_DOMAIN = "nvs.token-segment/1"
AXIS_DOMAIN = "nvs.token-axis/1"
UNKNOWN = "unknown"
_MISSING = object()

_PARENT_FIELDS = (
    "binding.n_in",
    "binding.n_gen",
    "capture_provenance.tokenizer_sha256",
    "capture_provenance.chat_template_sha256",
    "capture_provenance.prompt_ids_sha256",
    "capture_provenance.gen_token_ids_sha256",
    "model_build_id",
)
_COUNT = {"input": "binding.n_in", "generated": "binding.n_gen"}
_HASH = {
    "input": "capture_provenance.prompt_ids_sha256",
    "generated": "capture_provenance.gen_token_ids_sha256",
}
_IDENTITY = (
    ("tokenizer_sha256", "capture_provenance.tokenizer_sha256"),
    ("chat_template_sha256", "capture_provenance.chat_template_sha256"),
    ("model_build_id", "model_build_id"),
)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = load_schema(SCHEMA_PATH)
    reg = registry()
    reg = reg.with_resource(schema["$id"], Resource.from_contents(schema, DRAFT202012))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=reg)


def check_token_temporal(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any] | None,
    blobs: Mapping[str, bytes] | None,
) -> list[Violation]:
    """Schema first (alone if it fails); then every §7 check that fails."""
    stored = stored or {}
    blobs = blobs or {}
    schema_error = _schema_violation(envelope.get("payload"))
    if schema_error:
        return schema_error
    payload = envelope["payload"]
    out: list[Violation] = []
    if envelope.get("kind") != KIND:
        out.append(Violation("token_temporal_kind", f"kind {envelope.get('kind')!r} (expected {KIND!r})"))
    producer = envelope.get("producer")
    name = producer.get("name") if isinstance(producer, Mapping) else None
    if name != PRODUCER:
        out.append(Violation("token_temporal_producer", f"producer {name!r} (expected {PRODUCER!r})"))

    parent_id, parents_ok = _parent_id(envelope)
    if not parents_ok:
        out.append(
            Violation(
                "token_temporal_parents",
                f"parents must be exactly one role {PARENT_ROLE!r}, one artifact, ordered false",
            )
        )
    parent_payload, parent_known = _parent(envelope, stored, parent_id, out)
    values = _parent_values(parent_payload, parent_known, out)

    for segment in payload["segments"]:
        ref = segment["ids"]
        data = blobs.get(ref["uri"]) if isinstance(ref, Mapping) else None
        if data is None:
            out.append(
                Violation(
                    "token_temporal_blob_not_supplied",
                    f"{segment['origin']} ids blob {ref.get('uri') if isinstance(ref, Mapping) else None} is not supplied",
                )
            )
        else:
            out.extend(check_blob(ref, data))
        _count_and_hash(segment, values, out)
        _segment_id(payload, segment, out)
    _identity(payload, values, out)
    _axis_id(payload, out)
    return out


def _schema_violation(payload: Any) -> list[Violation]:
    errors = sorted(_validator().iter_errors(payload), key=lambda item: list(item.absolute_path))
    if not errors:
        return []
    first = errors[0]
    where = "/".join(str(part) for part in first.absolute_path)
    return [Violation("schema", f"payload/{where}: {first.message}")]


def _parent_id(envelope: Mapping[str, Any]) -> tuple[str | None, bool]:
    parents = envelope.get("parents")
    if not isinstance(parents, list) or len(parents) != 1:
        return None, False
    entry = parents[0]
    if not isinstance(entry, Mapping) or entry.get("role") != PARENT_ROLE or entry.get("ordered") is not False:
        return None, False
    ids = entry.get("artifact_ids")
    if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str):
        return None, False
    return ids[0], True


def _parent(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any],
    parent_id: str | None,
    out: list[Violation],
) -> tuple[Mapping[str, Any] | None, bool]:
    if parent_id is None:
        return None, False
    held = stored.get(parent_id)
    parent = held.get("envelope") if isinstance(held, Mapping) else None
    if not isinstance(parent, Mapping):
        out.append(Violation("token_temporal_parent", f"parent {parent_id} is not in stored"))
        return None, False
    schema = parent.get("payload_schema")
    ident = (schema.get("id"), schema.get("version")) if isinstance(schema, Mapping) else (None, None)
    if ident != (PARENT_SCHEMA_ID, PARENT_SCHEMA_VERSION):
        out.append(
            Violation(
                "token_temporal_parent",
                f"parent payload_schema {ident[0]} {ident[1]} (expected {PARENT_SCHEMA_ID} {PARENT_SCHEMA_VERSION})",
            )
        )
    if parent.get("observation_id") != envelope.get("observation_id"):
        out.append(Violation("token_temporal_parent", "observation_id differs from the parent"))
    if parent.get("session_id") != envelope.get("session_id"):
        out.append(Violation("token_temporal_parent", "session_id differs from the parent"))
    payload = parent.get("payload")
    if not isinstance(payload, Mapping):
        out.append(Violation("token_temporal_parent", "parent payload is missing"))
        return None, False
    return payload, True


def _parent_values(
    payload: Mapping[str, Any] | None,
    known: bool,
    out: list[Violation],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if not known or payload is None:
        return values
    for path in _PARENT_FIELDS:
        value = _dig(payload, path)
        if value is _MISSING or value == UNKNOWN:
            out.append(Violation("token_temporal_parent", f"parent field {path} is unknown"))
            continue
        if path == "capture_provenance.chat_template_sha256" or value is not None:
            values[path] = value
        else:
            out.append(Violation("token_temporal_parent", f"parent field {path} is unknown"))
    return values


def _dig(payload: Mapping[str, Any], path: str) -> Any:
    node: Any = payload
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _count_and_hash(segment: Mapping[str, Any], values: dict[str, Any], out: list[Violation]) -> None:
    origin = segment["origin"]
    declared = segment["n"]
    shape = segment["ids"]["shape"]
    if declared != shape[0]:
        out.append(Violation("token_temporal_n", f"{origin} n {declared} != shape[0] {shape[0]}"))
    count = values.get(_COUNT[origin], _MISSING)
    if count is not _MISSING and declared != count:
        out.append(Violation("token_temporal_n", f"{origin} n {declared} != parent {_COUNT[origin]} {count}"))
    parent_hash = values.get(_HASH[origin], _MISSING)
    if parent_hash is not _MISSING and segment["ids"]["sha256"] != parent_hash:
        out.append(
            Violation(
                "token_temporal_hash",
                f"{origin} ids.sha256 differs from parent {_HASH[origin]}",
            )
        )


def _identity(payload: Mapping[str, Any], values: dict[str, Any], out: list[Violation]) -> None:
    for field, path in _IDENTITY:
        parent = values.get(path, _MISSING)
        if parent is _MISSING:
            continue
        if payload[field] != parent:
            out.append(Violation("token_temporal_identity", f"{field} differs from parent {path}"))


def _segment_id(payload: Mapping[str, Any], segment: Mapping[str, Any], out: list[Violation]) -> None:
    expect = hashlib.sha256(
        jcs(
            {
                "domain": SEGMENT_DOMAIN,
                "tokenizer_sha256": payload["tokenizer_sha256"],
                "ids_sha256": segment["ids"]["sha256"],
                "n": segment["n"],
            }
        )
    ).hexdigest()
    if segment["segment_id"] != expect:
        out.append(Violation("token_temporal_segment_id", f"{segment['origin']} segment_id differs from the recomputed id"))


def _axis_id(payload: Mapping[str, Any], out: list[Violation]) -> None:
    expect = hashlib.sha256(
        jcs(
            {
                "domain": AXIS_DOMAIN,
                "segments": [
                    {"origin": segment["origin"], "segment_id": segment["segment_id"]}
                    for segment in payload["segments"]
                ],
            }
        )
    ).hexdigest()
    if payload["axis_id"] != expect:
        out.append(Violation("token_temporal_axis_id", "axis_id differs from the recomputed id"))
