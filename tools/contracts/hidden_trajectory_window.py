"""HT-20: the extra check of a window of a hidden trajectory (design U5 v0.2 section 7, W-1 .. W-4).

``check_window_space(envelope, stored, *, registry=None) -> HiddenTrajectoryResult``

An ``msr.trajectory-window`` 0.10.0 payload has no ``row_rule`` (IC-02, ``additionalProperties: false``), so the
space of the window is derived again from the parent's materials and the window's position and compared with the
envelope's ``space_id``. No string prefix is compared.

How to call (U6T-1): for an envelope whose ``payload_schema.id`` is ``msr.trajectory-window``, call
``gate_nvs.check_nvs_payload`` (that is the IC-02 check, ``list[Violation]``, unchanged) **and** this function, and
read both results. This function is not part of ``check_nvs_payload`` so that the return type of ``msr.*`` stays
``list[Violation]`` and UNVERIFIABLE can be returned. IC-02 does not depend on ``nvs.hidden-trajectory``, and
``ic02_window.py`` / ``gate.py`` / ``schemas.py`` are not changed.

Scope: ``msr.trajectory-window`` ``0.10.0`` only. Any other id or version (0.9.0 too) gives an empty result.

======================= ============================================================ ==========================
W-1                     window ``model_build_id`` / ``layer`` (type-exact) /          ``E_WIN_PARENT_FIELDS``
                        ``dimension`` equal the parent's; ``source`` is ``"T-hid"``
W-2                     the parent's ``row_rule`` is a base rule of the registry      ``E_WIN_PARENT_ROW_RULE``
W-3                     ``derived = parent.row_rule + "+rows" + start + "+" +         --
                        length + "/1"`` (``prefix_rows`` and ``rows`` alike)
W-4                     the window's ``space_id`` is ``hid_space(parent materials,    ``E_WIN_SPACE``
                        row_rule=derived)``
======================= ============================================================ ==========================

UNVERIFIABLE ``window_space_derivation`` / ``rule_not_derivable``: the parent is not found (IC-02 reports that
itself), is not ``nvs.hidden-trajectory`` 0.1.0, has a ``row_rule`` that is not a base form, or has materials from
which no space can be computed. The result is returned early only when the parent cannot be fetched.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from contracts.check import Violation
from contracts.hid_space import SpaceInputError, hid_space
from contracts.hidden_trajectory import (
    PAYLOAD_SCHEMA_ID,
    PAYLOAD_SCHEMA_VERSION,
    RULE_NOT_DERIVABLE,
    HiddenTrajectoryResult,
    Unverifiable,
    row_rule_registry,
)
from contracts.ic02_window import SOURCE_ROLE, V0100, WINDOW_SCHEMA, _one_parent

E_WIN_PARENT_FIELDS: Final = "E_WIN_PARENT_FIELDS"
E_WIN_PARENT_ROW_RULE: Final = "E_WIN_PARENT_ROW_RULE"
E_WIN_SPACE: Final = "E_WIN_SPACE"
WINDOW_SPACE_DERIVATION: Final = "window_space_derivation"
DERIVATION_VERSION: Final = 1
HID_SOURCE: Final = "T-hid"

_BASE_RULE = re.compile(
    r"[a-z0-9]+(?:-[a-z0-9]+)*-(?:block-out|mlp-out|final-norm)/[1-9][0-9]*"
)
_MISSING: Final = object()


def derived_row_rule(parent_row_rule: str, start: int, length: int) -> str:
    """W-3: the row rule of the window space."""
    return f"{parent_row_rule}+rows{start}+{length}/{DERIVATION_VERSION}"


def _same(a: Any, b: Any) -> bool:
    """Equal and of the same type (``15`` is not ``"15"``, ``True`` is not ``1``)."""
    return type(a) is type(b) and bool(a == b)


def _parent_envelope(
    envelope: Mapping[str, Any], stored: Mapping[str, Any] | None
) -> Mapping[str, Any] | None:
    parent_id = _one_parent(envelope, SOURCE_ROLE)
    if parent_id is None or not stored:
        return None
    held = stored.get(parent_id)
    if isinstance(held, Mapping) and isinstance(held.get("envelope"), Mapping):
        env: Mapping[str, Any] = held["envelope"]
        return env
    return held if isinstance(held, Mapping) else None


def check_window_space(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any] | None = None,
    *,
    registry: Mapping[str, Mapping[str, str]] | None = None,
) -> HiddenTrajectoryResult:
    """W-1 .. W-4 for an ``msr.trajectory-window`` 0.10.0 envelope that passed the IC-02 payload schema.

    ``stored``: artifact_id -> ``{"envelope": ...}``. Violations are collected, not stopped at the first.
    """
    schema = envelope.get("payload_schema")
    if not isinstance(schema, Mapping) or (
        schema.get("id"),
        schema.get("version"),
    ) != (WINDOW_SCHEMA, V0100):
        return HiddenTrajectoryResult()
    rules = row_rule_registry() if registry is None else registry
    out: list[Violation] = []
    unverifiable: list[Unverifiable] = []

    def not_derivable() -> None:
        item = Unverifiable(WINDOW_SPACE_DERIVATION, RULE_NOT_DERIVABLE)
        if item not in unverifiable:
            unverifiable.append(item)

    parent = _parent_envelope(envelope, stored)
    if parent is None:
        not_derivable()
        return HiddenTrajectoryResult((), tuple(unverifiable))
    pschema = parent.get("payload_schema")
    if not isinstance(pschema, Mapping) or (
        pschema.get("id"),
        pschema.get("version"),
    ) != (
        PAYLOAD_SCHEMA_ID,
        PAYLOAD_SCHEMA_VERSION,
    ):
        not_derivable()
        return HiddenTrajectoryResult((), tuple(unverifiable))
    pp = parent.get("payload")
    if not isinstance(pp, Mapping):
        not_derivable()
        return HiddenTrajectoryResult((), tuple(unverifiable))

    wp = envelope["payload"]
    # W-1
    for field in ("model_build_id", "layer", "dimension"):
        theirs = pp.get(field, _MISSING)
        if theirs is _MISSING or not _same(wp[field], theirs):
            out.append(
                Violation(
                    E_WIN_PARENT_FIELDS,
                    f"W-1 {field}: window {wp[field]!r} != parent {theirs!r}",
                )
            )
    if wp["source"] != HID_SOURCE:
        out.append(
            Violation(
                E_WIN_PARENT_FIELDS,
                f"W-1 source: {wp['source']!r} (the parent is a hidden trajectory: {HID_SOURCE!r})",
            )
        )
    # W-2
    row_rule = pp.get("row_rule")
    if not isinstance(row_rule, str) or not _BASE_RULE.fullmatch(row_rule):
        not_derivable()  # not a base form (a description, a window rule ...): W-3 and W-4 are not made
        return HiddenTrajectoryResult(tuple(out), tuple(unverifiable))
    if row_rule not in rules:
        out.append(
            Violation(
                E_WIN_PARENT_ROW_RULE,
                f"W-2 parent row_rule {row_rule!r} is not in the registry",
            )
        )
    # W-3
    window = wp["window"]
    derived = derived_row_rule(row_rule, window["start"], window["length"])
    # W-4
    try:
        expected = hid_space(
            model_build_id=pp.get("model_build_id"),
            layer=pp.get("layer"),
            row_rule=derived,
            compute_environment=pp.get("compute_environment"),
            dimension=pp.get("dimension"),
        )
    except SpaceInputError:
        not_derivable()  # the parent's materials cannot make a space (HT-05 says so for the parent itself)
    else:
        space_id = envelope.get("space_id")
        if space_id != expected:
            out.append(
                Violation(
                    E_WIN_SPACE,
                    f"W-4 space_id {space_id!r} != {expected!r} (derived row_rule {derived!r})",
                )
            )
    return HiddenTrajectoryResult(tuple(out), tuple(unverifiable))
