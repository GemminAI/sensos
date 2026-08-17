"""
sensos.evidence_accounting — SPEC-SENSOS-RTV2-001 v1.4 Section 7.4 G3 Evidence Integrity
=============================================================================================

Denominator-explicit five-state accounting, per v1.4 Section 7.4 G3:
"すべての報告において分母明記の5値Enum会計を適用し..." (apply
denominator-explicit five-state Enum accounting in every report), and
Section 7.2: "BLOCKED / NOT_EVALUABLE / NOT_IDENTIFIABLE を成功率計算から
勝手に除外してはいけない" (BLOCKED / NOT_EVALUABLE / NOT_IDENTIFIABLE must
not be silently excluded from success-rate calculations).

This module implements ONLY the pure tally/accounting utility — computing
a denominator-explicit count of ``ObservationState`` values. It does NOT
implement the full G3 deliverable set (an append-only
``raw_evidence_trace.jsonl`` writer, the AEC-graph + five-state-
distribution "Human Approval package" bundling) — those require real
Evidence records to write, and none exist yet (see Reality Audit; also
``sensos.evidence``, ``sensos.aec``). Building a file writer for records
that cannot yet be produced would be scaffolding without a real consumer.

No real Port evaluation data exists yet — tested against synthetic
ObservationState sequences.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sensos.observation_state import ObservationState


@dataclass(frozen=True)
class ObservationStateAccounting:
    """
    Denominator-explicit five-state accounting (v1.4 Section 7.4 G3).

    ``total`` is ALWAYS the full count of every input value, across all 5
    states — never a filtered subset. Any rate/fraction derived from this
    accounting must divide by ``total``, not by a count of only the
    "successful" states, per v1.4 Section 7.2's explicit prohibition on
    silently excluding BLOCKED / NOT_EVALUABLE / NOT_IDENTIFIABLE.
    """

    counts: Mapping[ObservationState, int]
    total: int

    def count(self, state: ObservationState) -> int:
        return self.counts.get(state, 0)

    def rate(self, state: ObservationState) -> float:
        """count(state) / total, where total is the full 5-state denominator."""
        return self.counts.get(state, 0) / self.total

    def as_fractions(self) -> dict[ObservationState, tuple[int, int]]:
        """
        {state: (count, total)} for every one of the 5 states — the
        (numerator, denominator) pair is always returned together, so a
        report built from this can never present a rate without its
        denominator alongside it.
        """
        return {state: (self.counts.get(state, 0), self.total) for state in ObservationState}


def tally_observation_states(states: Sequence[ObservationState]) -> ObservationStateAccounting:
    """
    Denominator-explicit tally of ``ObservationState`` values.

    Raises ValueError on an empty sequence (there is no meaningful
    denominator for zero observations) or on any element that is not an
    ``ObservationState`` member (fails loudly rather than silently
    dropping/miscounting an unrecognized value).
    """
    if not states:
        raise ValueError("states must not be empty — there is no denominator for zero observations")

    counts: dict[ObservationState, int] = {state: 0 for state in ObservationState}
    for s in states:
        if not isinstance(s, ObservationState):
            raise TypeError(f"expected ObservationState, got {s!r} ({type(s).__name__})")
        counts[s] += 1

    return ObservationStateAccounting(counts=counts, total=len(states))
