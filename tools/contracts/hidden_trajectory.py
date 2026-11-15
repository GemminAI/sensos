"""``nvs.hidden-trajectory`` 0.1.0: the semantic checks of the payload (design U5 v0.2, 4.3).

``check_hidden_trajectory(envelope, stored, blobs)`` first checks the payload against the schema
(``schema``, reported alone, in the form ``check_payload`` uses). A payload that passes the schema is then
put through HT-01 .. HT-17 and HT-19, **all of them, without stopping at the first failure**. The result
carries the violations and the checks that could not be made (UNVERIFIABLE, 4.4).

HT-18 (the binding to the RawObservationContract v2, 18a .. 18g) needs ``contract_facts`` (``contract_facts.py``,
verified by nvs-runtime; the Gate never reads the contract document). Without ``contract_facts`` it reports
UNVERIFIABLE ``contract_binding`` / ``contract_not_supplied``; with ``contract_ref`` null,
``contract_binding`` / ``contract_absent``. 18g (``facts.synthetic`` must be false, ``E_TRAJ_SYNTHETIC``) is made
whenever ``contract_facts`` is given, also when ``contract_ref`` is null (DC-U5-6): synthetic data must not pass.

Not here: the envelope itself (L1, ``ic00_versions.check_envelope_versioned``, which gives ``S4`` for a
producer that may not make the kind), the window checks (HT-20, U5-6), and the choice of checker by
``payload_schema`` (``gate_nvs.check_nvs_payload``).

The row-rule registry is data (``hid_row_rules.json``). It must equal sensos-inference
``observation.ROW_RULES`` (U1); that comparison is a task of the U1 side, because this module never imports
sensos-inference, nvs-runtime or nvs-kernel.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Final, NamedTuple

from contracts import ic00_v110
from contracts.blob import check_blob, check_float32_blob
from contracts.check import Violation, _s8
from contracts.contract_facts import validate_contract_facts
from contracts.hid_space import SpaceInputError, hid_space, hid_space_id
from contracts.hidden_trajectory_registry import hidden_trajectory_validator

SCHEMA_PATH: Final = "nvs/hidden-trajectory.schema.json"
PAYLOAD_SCHEMA_ID: Final = "nvs.hidden-trajectory"
PAYLOAD_SCHEMA_VERSION: Final = "0.1.0"
PRODUCER: Final = "sensos-inference"
PARENT_ROLE: Final = "generated_text"
REGISTRY_PATH: Final = Path(__file__).with_name("hid_row_rules.json")

# ----------------------------------------------------------------------------------------------- codes
E_KIND: Final = "E_TRAJ_KIND"
E_NO_OBSERVATION: Final = "E_TRAJ_NO_OBSERVATION"
E_PARENTS: Final = "E_TRAJ_PARENTS"
E_SHAPE: Final = "E_TRAJ_SHAPE"
E_SPACE_INPUT: Final = "E_TRAJ_SPACE_INPUT"
E_SPACE: Final = "E_TRAJ_SPACE"
E_ROW_RULE_UNKNOWN: Final = "E_TRAJ_ROW_RULE_UNKNOWN"
E_ROW_RULE_KIND: Final = "E_TRAJ_ROW_RULE_KIND"
E_ALIGNMENT: Final = "E_TRAJ_ALIGNMENT"
E_ROWS: Final = "E_TRAJ_ROWS"
E_POINT: Final = "E_TRAJ_POINT"
E_FINAL_NORM: Final = "E_TRAJ_FINAL_NORM"
E_RAW_REF: Final = "E_TRAJ_RAW_REF"
E_POLICY: Final = "E_TRAJ_POLICY"
E_UNKNOWNS: Final = "E_TRAJ_UNKNOWNS"
E_TOKEN_INDEX: Final = "E_TRAJ_TOKEN_INDEX"
E_CONTRACT: Final = "E_TRAJ_CONTRACT"
E_SYNTHETIC: Final = "E_TRAJ_SYNTHETIC"

# ----------------------------------------------------------------------- the UNVERIFIABLE catalogue (4.4)
# The source of truth is here, next to the checker (DC-7). One row per (payload_schema, check, reason).
BLOB_NOT_SUPPLIED: Final = "blob_not_supplied"
CONTRACT_NOT_SUPPLIED: Final = "contract_not_supplied"
CONTRACT_ABSENT: Final = "contract_absent"
CONTRACT_FIELD_UNKNOWN: Final = "contract_field_unknown"
RAW_NOT_IN_ARTIFACT: Final = "raw_not_in_artifact"
RULE_NOT_DERIVABLE: Final = "rule_not_derivable"

UNVERIFIABLE_CATALOG: Final[tuple[tuple[str, str, str], ...]] = (
    (PAYLOAD_SCHEMA_ID, "points_bytes", BLOB_NOT_SUPPLIED),
    (PAYLOAD_SCHEMA_ID, "token_index_bytes", BLOB_NOT_SUPPLIED),
    (PAYLOAD_SCHEMA_ID, "contract_binding", CONTRACT_NOT_SUPPLIED),
    (PAYLOAD_SCHEMA_ID, "contract_binding", CONTRACT_ABSENT),
    (PAYLOAD_SCHEMA_ID, "contract_binding.<field>", CONTRACT_FIELD_UNKNOWN),
    ("msr.trajectory-window", "window_rows", RAW_NOT_IN_ARTIFACT),  # IC-02
    ("msr.trajectory-window", "window_space_derivation", RULE_NOT_DERIVABLE),  # U5-6
)


class Unverifiable(NamedTuple):
    check: str
    reason: str


@dataclass(frozen=True)
class HiddenTrajectoryResult:
    violations: tuple[Violation, ...] = ()
    unverifiable: tuple[Unverifiable, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.violations


# ------------------------------------------------------------------------------------------ the registry


@cache
def _load_registry() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return data


def row_rule_registry() -> Mapping[str, Mapping[str, str]]:
    """``row_rule -> {"kind", "alignment"}`` (the base rules of ``hid_row_rules.json``)."""
    rules: Mapping[str, Mapping[str, str]] = _load_registry()["rules"]
    return rules


def _kind_slugs() -> Mapping[str, str]:
    slugs: Mapping[str, str] = _load_registry()["kind_slugs"]
    return slugs


_SLUG = re.compile(r"-(block-out|mlp-out|final-norm)/")
_POINT = re.compile(r"(final_norm)|(block_out|mlp_out):(0|[1-9][0-9]*)")
_ID_ALLOWED_KINDS = ic00_v110.PRODUCER_KINDS[
    PRODUCER
]  # IC-00 1.1.0: sensos-inference makes observations only


# ------------------------------------------------------------------------------------------------ helpers


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _pointer(parts: list[str]) -> str:
    return "".join("/" + p.replace("~", "~0").replace("/", "~1") for p in parts)


def _unknown_places(node: Any, path: list[str], out: list[str]) -> None:
    if isinstance(node, str):
        if node == "unknown":
            out.append(_pointer(path))
    elif isinstance(node, dict):
        for key, value in node.items():
            _unknown_places(value, [*path, str(key)], out)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _unknown_places(value, [*path, str(i)], out)


def _stored_envelope(held: Any) -> Mapping[str, Any]:
    if isinstance(held, Mapping) and isinstance(held.get("envelope"), Mapping):
        env: Mapping[str, Any] = held["envelope"]
        return env
    return held if isinstance(held, Mapping) else {}


def _schema_violation(payload: Any) -> list[Violation]:
    check = hidden_trajectory_validator(SCHEMA_PATH)
    errors = sorted(check.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if not errors:
        return []
    first = errors[0]
    return [
        Violation(
            "schema",
            f"payload/{'/'.join(str(p) for p in first.absolute_path)}: {first.message}",
        )
    ]


# ------------------------------------------------------------------------------------------- the checks


def _compare(
    field: str,
    mine: Any,
    theirs: Any,
    where: str,
    out: list[Violation],
    unverifiable: list[Unverifiable],
) -> None:
    """One 18a-18f comparison. ``"unknown"`` on either side: UNVERIFIABLE; two real values that differ: FAIL.
    The type is part of the value (``True`` is not ``1``)."""
    if mine == "unknown" or theirs == "unknown":
        unverifiable.append(
            Unverifiable(f"contract_binding.{field}", CONTRACT_FIELD_UNKNOWN)
        )
    elif type(mine) is not type(theirs) or mine != theirs:
        out.append(
            Violation(E_CONTRACT, f"{where}: payload {mine!r} != contract {theirs!r}")
        )


def _check_contract(
    envelope: Mapping[str, Any],
    payload: Mapping[str, Any],
    facts: Mapping[str, Any],
    out: list[Violation],
    unverifiable: list[Unverifiable],
) -> None:
    """18a .. 18f (18g is made by the caller). ``facts`` has the shape ``nvs.contract-facts/1``."""
    ref, contract = payload["contract_ref"], facts["contract"]

    def same(field: str, mine: Any, theirs: Any, where: str) -> None:
        _compare(field, mine, theirs, where, out, unverifiable)

    # 18a
    for key in ("name", "version", "contract_sha256"):
        if type(ref[key]) is not type(contract[key]) or ref[key] != contract[key]:
            out.append(
                Violation(
                    E_CONTRACT,
                    f"18a contract_ref.{key} {ref[key]!r} != contract {contract[key]!r}",
                )
            )
    # 18b
    point = payload["point"]
    position = facts["positions"].get(point)
    binding, mine = facts["binding"], payload["binding"]
    if position is None:
        out.append(
            Violation(
                E_CONTRACT, f"18b point {point!r} is not among the contract's positions"
            )
        )
    else:
        # 18c
        same(
            "trajectory_id",
            payload["raw_ref"]["trajectory_id"],
            position["trajectory_id"],
            "18c trajectory_id",
        )
        same("row_rule", payload["row_rule"], position["row_rule"], "18c row_rule")
        same("dimension", payload["dimension"], position["dimension"], "18c dimension")
        same(
            "final_norm_applied",
            payload["final_norm_applied"],
            position["final_norm_applied"],
            "18c final_norm_applied",
        )
        same(
            "stored_range.steps",
            payload["length"],
            position["stored_range"]["steps"],
            "18c stored_range.steps != length",
        )
        first = position["stored_range"]["first_row_pos"]
        same(
            "stored_range.first_row_pos",
            mine["n_in"] - 1,
            first,
            "18c stored_range.first_row_pos != n_in - 1",
        )
        # 18e
        try:
            expected = hid_space_id(position["space"])
        except SpaceInputError as exc:
            out.append(
                Violation(
                    E_CONTRACT,
                    f"18e the contract's space cannot be computed: {exc.message}",
                )
            )
        else:
            if envelope.get("space_id") != expected:
                out.append(
                    Violation(
                        E_CONTRACT,
                        f"18e space_id {envelope.get('space_id')!r} != the contract's {expected!r}",
                    )
                )
    # 18d
    for key in ("alignment", "n_in", "n_gen", "finish_reason"):
        same(key, mine[key], binding[key], f"18d binding.{key}")
    # 18f
    provenance = payload["capture_provenance"]
    same(
        "weights_sha256",
        provenance["weights_sha256"],
        facts["origin"]["weights_sha256"],
        "18f weights_sha256",
    )
    for key in (
        "tokenizer_sha256",
        "chat_template_sha256",
        "prompt_ids_sha256",
        "gen_token_ids_sha256",
    ):
        same(key, provenance[key], binding[key], f"18f {key}")


def check_hidden_trajectory(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any] | None = None,
    blobs: Mapping[str, bytes] | None = None,
    *,
    registry: Mapping[str, Mapping[str, str]] | None = None,
    contract_facts: Mapping[str, Any] | None = None,
) -> HiddenTrajectoryResult:
    """Schema first (alone if it fails); then HT-01 .. HT-17 and HT-19, all of them.

    ``stored``: artifact_id -> ``{"envelope": ...}`` (as in ``gate.check_payload``). ``blobs``: Blob uri ->
    bytes. ``registry`` is for tests; it defaults to ``hid_row_rules.json``.
    """
    if contract_facts is not None:
        validate_contract_facts(
            contract_facts
        )  # a wrong shape raises ContractFactsError (caller's error)
    payload = envelope.get("payload")
    bad = _schema_violation(payload)
    if bad:
        return HiddenTrajectoryResult(violations=tuple(bad))
    assert isinstance(payload, Mapping)
    rules = row_rule_registry() if registry is None else registry
    stored = stored or {}
    blobs = blobs or {}
    out: list[Violation] = []
    unverifiable: list[Unverifiable] = []

    def fail(code: str, message: str) -> None:
        out.append(Violation(code, message))

    # HT-01 .. HT-03: the envelope fields this contract fixes
    kind, producer = envelope.get("kind"), envelope.get("producer")
    name = producer.get("name") if isinstance(producer, Mapping) else None
    if kind not in _ID_ALLOWED_KINDS or name != PRODUCER:
        fail(
            E_KIND,
            f"kind {kind!r} / producer {name!r} (expected an observation from {PRODUCER!r})",
        )
    if envelope.get("observation_id") is None:
        fail(E_NO_OBSERVATION, "observation_id is null")
    parents = envelope.get("parents") or []
    if parents and not (
        len(parents) == 1
        and parents[0].get("role") == PARENT_ROLE
        and len(parents[0].get("artifact_ids", [])) == 1
    ):
        fail(
            E_PARENTS,
            f"parents must be none or exactly one artifact in role {PARENT_ROLE!r}",
        )

    length, dimension = payload["length"], payload["dimension"]
    # HT-04
    points, tix = payload["points"], payload["token_index"]
    if points["shape"] != [length, dimension]:
        fail(E_SHAPE, f"points.shape {points['shape']} != [{length}, {dimension}]")
    if tix["shape"] != [length]:
        fail(E_SHAPE, f"token_index.shape {tix['shape']} != [{length}]")

    # HT-05 / HT-06
    space_ok = True
    for field in ("model_build_id", "compute_environment"):
        if payload[field] in ("unknown", "not_applicable"):
            fail(
                E_SPACE_INPUT,
                f"{field} is a missing-value word ({payload[field]!r}); a space material cannot be missing",
            )
            space_ok = False
    if space_ok:
        try:
            expected_space = hid_space(
                model_build_id=payload["model_build_id"],
                layer=payload["layer"],
                row_rule=payload["row_rule"],
                compute_environment=payload["compute_environment"],
                dimension=payload["dimension"],
            )
        except SpaceInputError as exc:
            fail(E_SPACE_INPUT, exc.message)
        else:
            if envelope.get("space_id") != expected_space:
                fail(
                    E_SPACE,
                    f"space_id {envelope.get('space_id')!r} != recomputed {expected_space!r}",
                )
    else:
        # the other material may be broken too; report it as well
        try:
            hid_space(
                model_build_id="m",
                layer=payload["layer"],
                row_rule=payload["row_rule"],
                compute_environment="e",
                dimension=payload["dimension"],
            )
        except SpaceInputError as exc:
            fail(E_SPACE_INPUT, exc.message)

    # HT-07 .. HT-09
    row_rule = payload["row_rule"]
    base_ok = re.fullmatch(_load_registry()["base_rule_pattern"], row_rule) is not None
    registered = rules.get(row_rule) if base_ok else None
    if registered is None:
        fail(
            E_ROW_RULE_UNKNOWN,
            f"row_rule {row_rule!r} is not a base rule in the registry",
        )
    slug = _SLUG.search(row_rule)
    slug_kind = _kind_slugs().get(slug.group(1)) if slug else None
    if slug_kind != payload["kind"] or (
        registered is not None and registered["kind"] != payload["kind"]
    ):
        fail(
            E_ROW_RULE_KIND,
            f"row_rule {row_rule!r} does not make kind {payload['kind']!r}",
        )
    if (
        registered is not None
        and payload["binding"]["alignment"] != registered["alignment"]
    ):
        fail(
            E_ALIGNMENT,
            f"binding.alignment {payload['binding']['alignment']!r} != registry {registered['alignment']!r}",
        )

    # HT-10
    binding = payload["binding"]
    if length != binding["n_gen"] or binding["n_in"] < 1:
        fail(
            E_ROWS,
            f"length {length} vs n_gen {binding['n_gen']} (must be equal for decides-next/1), n_in {binding['n_in']} (>= 1)",
        )

    # HT-11
    point = _POINT.fullmatch(payload["point"])
    if point is None:
        fail(E_POINT, f"point {payload['point']!r} is not a point name")
    else:
        if point.group(1):
            want_kind, want_layer, want_position = (
                "final_norm",
                "final_norm",
                "final_norm",
            )
        else:
            want_kind, want_layer = point.group(2), int(point.group(3))  # type: ignore[assignment]
            want_position = f"L{want_layer}.{want_kind}"
        layer = payload["layer"]
        if (
            payload["kind"] != want_kind
            or payload["position"] != want_position
            or type(layer) is not type(want_layer)
            or layer != want_layer
        ):
            fail(
                E_POINT,
                f"point {payload['point']!r} gives kind {want_kind!r}, layer {want_layer!r}, position {want_position!r}",
            )

    # HT-12
    applied = payload["final_norm_applied"]
    if (payload["kind"] == "final_norm" and applied is not True) or (
        payload["kind"] == "mlp_out" and applied is not False
    ):
        fail(
            E_FINAL_NORM,
            f"final_norm_applied {applied!r} does not fit kind {payload['kind']!r}",
        )

    # HT-13
    if points["sha256"] != payload["raw_ref"]["trajectory_id"]:
        fail(E_RAW_REF, "points.sha256 != raw_ref.trajectory_id")
    if points["uri"] != "blob:sha256:" + points["sha256"]:
        fail("S34", "points.uri hex differs from sha256")

    # HT-14
    if (
        payload["policy"]["sha256"]
        != hashlib.sha256(payload["policy"]["name"].encode("utf-8")).hexdigest()
    ):
        fail(E_POLICY, "policy.sha256 is not the sha256 of policy.name")

    # HT-15
    places: list[str] = []
    _unknown_places({k: v for k, v in payload.items() if k != "unknowns"}, [], places)
    listed = [u["field"] for u in payload["unknowns"]]
    if len(set(listed)) != len(listed):
        fail(E_UNKNOWNS, "unknowns lists a field twice")
    if listed != sorted(listed, key=lambda s: s.encode("utf-8")):
        fail(E_UNKNOWNS, "unknowns is not in ascending order of field")
    for place in sorted(set(places) - set(listed)):
        fail(E_UNKNOWNS, f'{place} is "unknown" but not in unknowns')
    for place in sorted(
        p
        for p in places
        if not (p == "/state_dtype" or p.startswith("/capture_provenance/"))
    ):
        fail(
            E_UNKNOWNS,
            f'{place} cannot be "unknown" (only state_dtype and capture_provenance can)',
        )
    for place in sorted(set(listed) - set(places)):
        fail(E_UNKNOWNS, f'{place} is in unknowns but its value is not "unknown"')

    # HT-16
    raw = blobs.get(tix["uri"])
    if raw is None:
        unverifiable.append(Unverifiable("token_index_bytes", BLOB_NOT_SUPPLIED))
    else:
        out.extend(check_blob(tix, raw))
        values = struct.unpack(f"<{len(raw) // 8}q", raw[: len(raw) // 8 * 8])
        if len(raw) != 8 * length or list(values) != list(range(length)):
            fail(E_TOKEN_INDEX, f"token_index is not 0 .. {length - 1}")

    # HT-17
    data = blobs.get(points["uri"])
    if data is None:
        unverifiable.append(Unverifiable("points_bytes", BLOB_NOT_SUPPLIED))
    else:
        out.extend(
            v for v in check_float32_blob(points, data) if v.code != "S34"
        )  # S34 is HT-13's

    # HT-18 (the binding to the contract v2). 18g is made whenever facts are given.
    if contract_facts is not None and contract_facts["synthetic"] is True:
        fail(
            E_SYNTHETIC,
            "contract_facts.synthetic is true: synthetic data must not enter the chain",
        )
    if payload["contract_ref"] is None:
        unverifiable.append(Unverifiable("contract_binding", CONTRACT_ABSENT))
    elif contract_facts is None:
        unverifiable.append(Unverifiable("contract_binding", CONTRACT_NOT_SUPPLIED))
    else:
        _check_contract(envelope, payload, contract_facts, out, unverifiable)

    # HT-19
    known: list[Mapping[str, Any]] = []
    for entry in parents:
        if entry.get("role") != PARENT_ROLE:
            continue
        for aid in entry.get("artifact_ids", []):
            held = stored.get(aid)
            if held is None:
                fail("parent_unknown", str(aid))
            else:
                known.append(_stored_envelope(held))
    if known:
        out.extend(_s8(envelope, known))

    return HiddenTrajectoryResult(
        violations=tuple(out), unverifiable=tuple(unverifiable)
    )
