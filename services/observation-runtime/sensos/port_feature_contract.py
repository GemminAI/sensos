"""
sensos.port_feature_contract — SPEC-SENSOS-RTV2-001 v1.4 Section 5.2
=========================================================================

Runtime type + validation for the per-Port feature-extraction contract
schema. v1.4 gives exactly ONE worked example (Port P17):

    port_feature_contract:
      port_id: P17
      output_dim: 1
      readout_source: "curvature"
      layer_range: [12, 24]
      reduction: "L2norm"
      standardize: true

This module implements the schema SHAPE and its validation rules only. The
individual f_i (which of the 38 fixed Ports maps to which
output_dim/readout_source/layer_range/reduction) is NOT defined here for
ports other than the one worked example — that is BLOCKED_BY_SPEC_DECISION
(v1.4 gives no per-port mapping for the other 37 Ports; inventing one would
be fabricating spec content). The 38-Port SSOT itself (v1.4 Section 5.1:
P01-P11 / P12-P22 / P23-P31 / P32-P38, 31 session-scoped + 7 stateless,
fixed) is treated as authoritative and is NOT re-derived, reduced, or
altered here.

Two fields — ``readout_source`` and ``reduction`` — are free-form strings,
not closed enums, because v1.4 Section 5.2 gives exactly one example value
for each ("curvature", "L2norm") without ever enumerating the full valid
set. Treating either as a closed enum would mean inventing membership v1.4
never states; this is flagged, not decided.

``standardize`` IS validated strictly: v1.4 Section 5.2 states
standardization against the Stateless pool is a MUST for every Port, with
no per-port opt-out — so ``standardize=False`` is rejected outright, not
treated as a different valid configuration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# P01-P38 only, per the v1.4 Section 5.1 38-Port SSOT (zero-padded, no P00/P39+).
_PORT_ID_PATTERN = re.compile(r"^P(0[1-9]|[12][0-9]|3[0-8])$")


@dataclass(frozen=True)
class PortFeatureContract:
    """v1.4 Section 5.2 port_feature_contract schema, as a validated runtime type."""

    port_id: str
    output_dim: int
    readout_source: str
    layer_range: tuple[int, int]
    reduction: str
    standardize: bool

    def __post_init__(self) -> None:
        if not _PORT_ID_PATTERN.match(self.port_id):
            raise ValueError(
                f"port_id {self.port_id!r} is not a valid Port identifier; "
                "must be P01-P38 per the v1.4 Section 5.1 38-Port SSOT"
            )
        if self.output_dim <= 0:
            raise ValueError(f"output_dim must be > 0, got {self.output_dim}")
        if not self.readout_source:
            raise ValueError("readout_source must not be empty")
        if not self.reduction:
            raise ValueError("reduction must not be empty")

        layer_range = tuple(self.layer_range)
        if len(layer_range) != 2:
            raise ValueError(f"layer_range must have exactly 2 elements, got {self.layer_range!r}")
        lo, hi = layer_range
        if lo < 0 or hi < 0:
            raise ValueError(f"layer_range values must be non-negative, got {self.layer_range!r}")
        if lo > hi:
            raise ValueError(f"layer_range must be [start <= end], got {self.layer_range!r}")

        if self.standardize is not True:
            raise ValueError(
                "standardize must be True — v1.4 Section 5.2 requires z-score "
                "standardization against the Stateless pool for every Port, "
                "with no per-port opt-out"
            )
