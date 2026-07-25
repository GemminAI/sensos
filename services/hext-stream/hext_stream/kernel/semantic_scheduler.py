"""RFC-HEXT011 §5: Semantic Scheduler.

Reuses, rather than redefines, the EXP-4010 §5.1 gain formula already
implemented in ``processors/semantic/gain_scheduler.py``
(``compute_gain(sed, lcf) = exp(-alpha * SED) * floor(LCF)``). This module
is only the kernel-level enforcement point described in RFC-HEXT011 §5.1:
given an already-computed gain value, decide whether the Controller stage's
output is allowed to take effect, and detect the hard-lock condition.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    hard_locked: bool
    gain: float


class SemanticScheduler:
    """RFC-HEXT011 §5: gain-gated advancement for Controller stage output."""

    def gate(self, gain: float) -> GateDecision:
        """RFC-HEXT011 §5.1 / EXP-4010 §5.1: a gain of exactly 0.0 is the
        hard-lock condition (``floor(LCF) = 0``); any other gain value
        permits the Controller output to take effect. This does not
        recompute or alter the gain — it only gates on the value already
        produced by the existing ``GainScheduler`` processor.
        """
        hard_locked = gain == 0.0
        return GateDecision(allowed=not hard_locked, hard_locked=hard_locked, gain=gain)
