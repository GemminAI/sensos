"""DAK executive decision enumeration."""

from enum import Enum


class DAKDecision(Enum):
    """
    Multivalued executive actions dispatched by the Trajectory Differential Safety Kernel.
    """

    CONTINUE = "CONTINUE"   # Safe trajectory. Authorize local action.
    CORRECT = "CORRECT"     # Local deviation. Trigger cognitive state rewrite loop.
    RETRIEVE = "RETRIEVE"   # OOD context. Pull crystallized memory and inject.
    ESCALATE = "ESCALATE"   # High uncertainty. Escalate to cloud or higher cognitive tier.
    ABORT = "ABORT"         # Critical deviation. Immediate safe-state shutdown.
