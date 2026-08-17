"""
sensos.observation_state — SPEC-SENSOS-RTV2-001 v1.4 Section 7.2
==================================================================

The canonical 5-value evaluation state for a single Port, transcribed
verbatim from v1.4 §7.2. This is deliberately a separate type from
``sensos.dak.decision.DAKDecision`` — that enum (CONTINUE/CORRECT/RETRIEVE/
ESCALATE/ABORT) is DAK's own pre-existing risk-decision vocabulary and is
not part of this spec; the two must never be conflated or interchanged.

No component in this repository produces or consumes ``ObservationState``
values yet — it is a prerequisite type for TCK-v2 G1/G2/G3 (v1.4 §7.4),
none of which are implemented yet.
"""

from __future__ import annotations

from enum import Enum


class ObservationState(Enum):
    """v1.4 §7.2 Canonical Observation State Enum, verbatim."""

    INDIVIDUALLY_IDENTIFIABLE = "INDIVIDUALLY_IDENTIFIABLE"
    CLASS_IDENTIFIABLE = "CLASS_IDENTIFIABLE"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"
    NOT_EVALUABLE = "NOT_EVALUABLE"
    BLOCKED = "BLOCKED"
