"""``contract_facts`` (version ``nvs.contract-facts/1``): the verified fields of a RawObservationContract v2
that the Gate compares with an ``nvs.hidden-trajectory`` envelope (design U5 v0.2, 5.2; DC-U5-5, DC-U5-6).

The Gate never reads the contract document. nvs-runtime (U6) verifies the document and its
``contract_sha256``, copies the verified fields into this shape, and passes it to the Gate;
``contract_facts_from_v2`` (document -> facts) is that U6 task and is not here.

``validate_contract_facts`` checks the **shape** only: the keys, the types, ``contract.version == 2``, the
six keys of each ``space`` and the type of ``layer`` (design 2.1). A facts of the wrong shape is an error of
the caller, not a violation of the thing checked: it is **raised** as ``ContractFactsError`` (code
``gate_internal_error``) and is never put among the ``violations``.

A value the contract could not establish is the string ``"unknown"`` and is allowed where the contract allows
it: ``weights_sha256``, the four other hashes of ``binding``, ``trajectory_id``, ``final_norm_applied`` (of a
``block_out`` position), ``stored_range.*``, ``n_in`` and ``n_gen``. ``chat_template_sha256`` may also be
``"not_applicable"``. A comparison with an ``"unknown"`` is UNVERIFIABLE, never a failure.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from contracts.errors import ContractError
from contracts.hid_space import MATERIAL_KEYS

FACTS_VERSION: Final = "nvs.contract-facts/1"
E_GATE_INTERNAL: Final = "gate_internal_error"
UNKNOWN: Final = "unknown"
NOT_APPLICABLE: Final = "not_applicable"
CONTRACT_NAME: Final = "RawObservationContract"
CONTRACT_VERSION: Final = 2

TOP_KEYS: Final = (
    "facts_version",
    "contract",
    "synthetic",
    "binding",
    "origin",
    "positions",
)
CONTRACT_KEYS: Final = ("name", "version", "contract_sha256")
BINDING_KEYS: Final = (
    "alignment",
    "n_in",
    "n_gen",
    "finish_reason",
    "tokenizer_sha256",
    "chat_template_sha256",
    "prompt_ids_sha256",
    "gen_token_ids_sha256",
)
ORIGIN_KEYS: Final = ("model_build_id", "compute_environment", "weights_sha256")
POSITION_KEYS: Final = (
    "trajectory_id",
    "row_rule",
    "dimension",
    "final_norm_applied",
    "stored_range",
    "space",
)
STORED_RANGE_KEYS: Final = ("steps", "first_row_pos")

_HEX64 = re.compile(r"[0-9a-f]{64}")


class ContractFactsError(ContractError):
    """``contract_facts`` has the wrong shape (``code`` is ``gate_internal_error``)."""

    def __init__(self, message: str) -> None:
        super().__init__(E_GATE_INTERNAL, message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _keys(node: Any, where: str, keys: tuple[str, ...]) -> Mapping[str, Any]:
    if not isinstance(node, Mapping):
        raise ContractFactsError(f"{where}: must be a mapping")
    present = set(node)
    if present != set(keys):
        missing = sorted(set(keys) - present)
        extra = sorted(present - set(keys), key=str)
        raise ContractFactsError(
            f"{where}: keys must be exactly {list(keys)}; missing {missing}, extra {extra}"
        )
    return node


def _string(value: Any, where: str) -> None:
    if not isinstance(value, str) or not value:
        raise ContractFactsError(f"{where}: must be a non-empty string")


def _hex(value: Any, where: str, *extra: str) -> None:
    ok = isinstance(value, str) and (
        _HEX64.fullmatch(value) is not None or value in (UNKNOWN, *extra)
    )
    if not ok:
        allowed = " or ".join(
            ["64 lowercase hex characters", f"{UNKNOWN!r}", *[repr(e) for e in extra]]
        )
        raise ContractFactsError(f"{where}: must be {allowed}")


def _count(value: Any, where: str, minimum: int, *, unknown: bool) -> None:
    if unknown and value == UNKNOWN and isinstance(value, str):
        return
    if not _is_int(value) or value < minimum:
        raise ContractFactsError(
            f"{where}: must be an integer >= {minimum}"
            + (f" or {UNKNOWN!r}" if unknown else "")
        )


def _validate_position(point: str, position: Any) -> None:
    where = f"positions[{point!r}]"
    pos = _keys(position, where, POSITION_KEYS)
    _hex(pos["trajectory_id"], f"{where}.trajectory_id")
    _string(pos["row_rule"], f"{where}.row_rule")
    if not _is_int(pos["dimension"]):
        raise ContractFactsError(f"{where}.dimension: must be an integer")
    applied = pos["final_norm_applied"]
    if not isinstance(applied, bool) and applied != UNKNOWN:
        raise ContractFactsError(
            f"{where}.final_norm_applied: must be a boolean or {UNKNOWN!r}"
        )
    stored = _keys(pos["stored_range"], f"{where}.stored_range", STORED_RANGE_KEYS)
    for key in STORED_RANGE_KEYS:
        _count(stored[key], f"{where}.stored_range.{key}", 0, unknown=True)
    space = _keys(pos["space"], f"{where}.space", MATERIAL_KEYS)
    for key in ("model_build_id", "row_rule", "compute_environment", "space_rule"):
        _string(space[key], f"{where}.space.{key}")
    layer = space["layer"]
    if not (_is_int(layer) and layer >= 0) and layer != "final_norm":
        raise ContractFactsError(
            f"{where}.space.layer: must be an integer >= 0 or 'final_norm', not {layer!r}"
        )
    if not _is_int(space["dimension"]):
        raise ContractFactsError(f"{where}.space.dimension: must be an integer")


def validate_contract_facts(facts: Any) -> None:
    """Return ``None`` if ``facts`` has the shape of ``nvs.contract-facts/1``; else raise ``ContractFactsError``."""
    top = _keys(facts, "contract_facts", TOP_KEYS)
    if top["facts_version"] != FACTS_VERSION:
        raise ContractFactsError(
            f"facts_version: must be {FACTS_VERSION!r}, not {top['facts_version']!r}"
        )
    contract = _keys(top["contract"], "contract", CONTRACT_KEYS)
    _string(contract["name"], "contract.name")
    if not _is_int(contract["version"]) or contract["version"] != CONTRACT_VERSION:
        raise ContractFactsError(
            f"contract.version: must be the integer {CONTRACT_VERSION}, not {contract['version']!r}"
        )
    sha = contract["contract_sha256"]
    if not isinstance(sha, str) or _HEX64.fullmatch(sha) is None:
        raise ContractFactsError(
            "contract.contract_sha256: must be 64 lowercase hex characters"
        )
    if not isinstance(top["synthetic"], bool):
        raise ContractFactsError("synthetic: must be a boolean")
    binding = _keys(top["binding"], "binding", BINDING_KEYS)
    _string(binding["alignment"], "binding.alignment")
    _string(binding["finish_reason"], "binding.finish_reason")
    _count(binding["n_in"], "binding.n_in", 1, unknown=True)
    _count(binding["n_gen"], "binding.n_gen", 1, unknown=True)
    for key in ("tokenizer_sha256", "prompt_ids_sha256", "gen_token_ids_sha256"):
        _hex(binding[key], f"binding.{key}")
    _hex(
        binding["chat_template_sha256"], "binding.chat_template_sha256", NOT_APPLICABLE
    )
    origin = _keys(top["origin"], "origin", ORIGIN_KEYS)
    _string(origin["model_build_id"], "origin.model_build_id")
    _string(origin["compute_environment"], "origin.compute_environment")
    _hex(origin["weights_sha256"], "origin.weights_sha256")
    positions = top["positions"]
    if not isinstance(positions, Mapping) or not positions:
        raise ContractFactsError(
            "positions: must be a non-empty mapping (point name -> position)"
        )
    for point, position in positions.items():
        if not isinstance(point, str) or not point:
            raise ContractFactsError(
                f"positions: the key {point!r} must be a point name (string)"
            )
        _validate_position(point, position)
