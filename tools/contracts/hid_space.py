"""``space_id`` of a hidden-trajectory (``hid:``): the inputs, their checks, and the hash.

A space is named by six materials: ``model_build_id``, ``layer``, ``row_rule``,
``compute_environment``, ``dimension`` and the constant ``space_rule``. ``kind``, ``point`` and
``binding`` are not materials: the kind is told apart by the ``row_rule`` name. ``layer`` goes in
as the number it is (``15`` and ``"15"`` are different spaces; ``"15"`` is refused). The rule name
stays ``nvs.hidden-trajectory.space/1``.

    space_id = "hid:" + BLAKE2b-256(JCS(materials)).hexdigest()      # 68 characters

The same expression as ``examples/pb_path/ids_cli.py`` (``hid_space``) of nvs-runtime, so ids stored
there do not change. Every violation of an input is a ``SpaceInputError`` (code
``E_TRAJ_SPACE_INPUT``); nothing is repaired and an unknown key is never ignored.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any, Final

from contracts.errors import ContractError
from contracts.jcs import MAX_SAFE, jcs

SPACE_RULE: Final = "nvs.hidden-trajectory.space/1"
E_TRAJ_SPACE_INPUT: Final = "E_TRAJ_SPACE_INPUT"
MATERIAL_KEYS: Final = (
    "model_build_id",
    "layer",
    "row_rule",
    "compute_environment",
    "dimension",
    "space_rule",
)
FINAL_NORM: Final = "final_norm"
MAX_DIMENSION: Final = 65535

_NAME = re.compile(r"[A-Za-z0-9._:/+@=-]{1,256}")
#: ``family-runtime-kind_slug/version``, optionally followed by a window: ``+rows<start>+<length>/<dversion>``.
_ROW_RULE = re.compile(
    r"[a-z0-9]+(?:-[a-z0-9]+)*-(?:block-out|mlp-out|final-norm)/[1-9][0-9]*"
    r"(?:\+rows(?:0|[1-9][0-9]*)\+[1-9][0-9]*/[1-9][0-9]*)?"
)


class SpaceInputError(ContractError):
    """An input of ``space_id`` breaks its rule (``code`` is ``E_TRAJ_SPACE_INPUT``)."""

    def __init__(self, message: str) -> None:
        super().__init__(E_TRAJ_SPACE_INPUT, message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _name(field: str, value: Any) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise SpaceInputError(
            f"{field} must match [A-Za-z0-9._:/+@=-]{{1,256}}, got {value!r}"
        )
    return str(value)


def _layer(value: Any) -> int | str:
    if isinstance(value, str):
        if value != FINAL_NORM:
            raise SpaceInputError(
                f"layer must be an integer >= 0 or {FINAL_NORM!r}, got the string {value!r}"
            )
        return FINAL_NORM
    if not _is_int(value) or not 0 <= value <= MAX_SAFE:
        raise SpaceInputError(
            f"layer must be an integer in 0..{MAX_SAFE} or {FINAL_NORM!r}, got {value!r}"
        )
    return int(value)


def _row_rule(value: Any) -> str:
    if not isinstance(value, str) or not _ROW_RULE.fullmatch(value):
        raise SpaceInputError(
            f"row_rule is not a base or window row rule name: {value!r}"
        )
    return str(value)


def _dimension(value: Any) -> int:
    if not _is_int(value) or not 1 <= value <= MAX_DIMENSION:
        raise SpaceInputError(
            f"dimension must be an integer in 1..{MAX_DIMENSION}, got {value!r}"
        )
    return int(value)


def hid_space_materials(
    *,
    model_build_id: Any,
    layer: Any,
    row_rule: Any,
    compute_environment: Any,
    dimension: Any,
) -> dict[str, Any]:
    """The checked materials (``space_rule`` added). ``SpaceInputError`` on any violation."""
    return {
        "model_build_id": _name("model_build_id", model_build_id),
        "layer": _layer(layer),
        "row_rule": _row_rule(row_rule),
        "compute_environment": _name("compute_environment", compute_environment),
        "dimension": _dimension(dimension),
        "space_rule": SPACE_RULE,
    }


def hid_space_id(materials: Mapping[str, Any]) -> str:
    """``hid:`` + 64 lowercase hex characters, from exactly the six materials.

    A missing or an extra key, a value that fails its check, and a ``space_rule`` other than
    ``SPACE_RULE`` (``/2``, say) are a ``SpaceInputError``."""
    if not isinstance(materials, Mapping):
        raise SpaceInputError("materials must be a mapping")
    keys = set(materials)
    if keys != set(MATERIAL_KEYS):
        missing = sorted(set(MATERIAL_KEYS) - keys, key=str)
        extra = sorted(keys - set(MATERIAL_KEYS), key=str)
        raise SpaceInputError(
            f"materials must have exactly {list(MATERIAL_KEYS)}; missing {missing}, extra {extra}"
        )
    if (
        not isinstance(materials["space_rule"], str)
        or materials["space_rule"] != SPACE_RULE
    ):
        raise SpaceInputError(
            f"space_rule must be exactly {SPACE_RULE!r}, got {materials['space_rule']!r}"
        )
    checked = hid_space_materials(
        model_build_id=materials["model_build_id"],
        layer=materials["layer"],
        row_rule=materials["row_rule"],
        compute_environment=materials["compute_environment"],
        dimension=materials["dimension"],
    )
    return "hid:" + hashlib.blake2b(jcs(checked), digest_size=32).hexdigest()


def hid_space(
    *,
    model_build_id: Any,
    layer: Any,
    row_rule: Any,
    compute_environment: Any,
    dimension: Any,
) -> str:
    """``hid_space_id(hid_space_materials(...))``."""
    return hid_space_id(
        hid_space_materials(
            model_build_id=model_build_id,
            layer=layer,
            row_rule=row_rule,
            compute_environment=compute_environment,
            dimension=dimension,
        )
    )


__all__ = [
    "E_TRAJ_SPACE_INPUT",
    "MATERIAL_KEYS",
    "SPACE_RULE",
    "SpaceInputError",
    "hid_space",
    "hid_space_id",
    "hid_space_materials",
]
