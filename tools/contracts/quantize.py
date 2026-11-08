"""Section 7: quantization to integers.

``q = round_ties_to_even(value * 2**(-exponent))``. ``math.ldexp`` scales
exactly; the built-in ``round()`` on a float is ties-to-even (not
``numpy.rint``; no dependency needed).
"""

from __future__ import annotations

import math

from contracts.errors import E_QUANT_NONFINITE, E_QUANT_RANGE, ContractError

MAX_SAFE = 2**53 - 1
ENVELOPE_RANGE = (-MAX_SAFE, MAX_SAFE)
INT64_RANGE = (-(2**63), 2**63 - 1)


def quantize(
    value: float,
    exponent: int,
    *,
    int_range: tuple[int, int] = ENVELOPE_RANGE,
) -> int:
    if isinstance(value, bool) or not isinstance(value, float | int):
        raise ContractError(E_QUANT_NONFINITE, "value must be a float or int")
    as_float = float(value)
    if not math.isfinite(as_float):
        raise ContractError(E_QUANT_NONFINITE, "NaN and infinity cannot be quantized")
    try:
        scaled = math.ldexp(as_float, -exponent)
    except OverflowError as exc:
        raise ContractError(E_QUANT_RANGE, "value too large for the quantum") from exc
    if not math.isfinite(scaled):  # pragma: no cover - ldexp raises instead
        raise ContractError(E_QUANT_RANGE, "value too large for the quantum")
    q = round(scaled)  # float -> int, ties-to-even
    lo, hi = int_range
    if not lo <= q <= hi:
        raise ContractError(E_QUANT_RANGE, f"{q} outside [{lo}, {hi}]")
    return int(q)


def dequantize(
    q: int,
    exponent: int,
    *,
    int_range: tuple[int, int] = ENVELOPE_RANGE,
) -> float:
    if isinstance(q, bool) or not isinstance(q, int):
        raise ContractError(E_QUANT_RANGE, "q must be an int")
    lo, hi = int_range
    if not lo <= q <= hi:
        raise ContractError(E_QUANT_RANGE, f"{q} outside [{lo}, {hi}]")
    return math.ldexp(float(q), exponent)
