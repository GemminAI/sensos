"""Section 5, step 0: the parsing stage of the Integration Gate.

Rejects, before schema validation and JCS: bytes that are not UTF-8, lone
surrogates (written as ``\\ud800`` escapes), number tokens with a decimal point
or exponent (even when the value is integral), ``NaN``/``Infinity``, and
duplicate keys inside one object (compared after unescaping).
"""

from __future__ import annotations

import json
from typing import Any, NoReturn

from contracts.errors import (
    E_CONSTANT,
    E_DUP_KEY,
    E_FLOAT_TOKEN,
    E_SURROGATE,
    E_SYNTAX,
    E_UTF8,
    ContractError,
)


def _float_token(token: str) -> NoReturn:
    raise ContractError(E_FLOAT_TOKEN, f"number token {token!r} has a fraction or exponent")


def _constant(token: str) -> NoReturn:
    raise ContractError(E_CONSTANT, f"{token} is not allowed")


def _has_lone_surrogate(text: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if _has_lone_surrogate(key):
            raise ContractError(E_SURROGATE, "lone surrogate in an object key")
        if key in out:
            raise ContractError(E_DUP_KEY, f"duplicate key {key!r}")
        out[key] = value
    return out


def _check_strings(value: Any) -> None:
    if isinstance(value, str):
        if _has_lone_surrogate(value):
            raise ContractError(E_SURROGATE, "lone surrogate in a string")
    elif isinstance(value, list):
        for item in value:
            _check_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            _check_strings(item)


def strict_load(data: bytes) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError(E_UTF8, str(exc)) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_float_token,
            parse_constant=_constant,
        )
    except ContractError:
        raise
    except (ValueError, RecursionError) as exc:
        raise ContractError(E_SYNTAX, str(exc)) from exc
    _check_strings(value)
    return value
