"""RFC-HEXT016 §9 Rule 6: exactly one theory-execution deferral point.

Prior to this module, two independent, near-identical
`TheorySwitchingNotImplementedError` classes existed — one in
`hext_stream/devtools/replay_controller.py`, one in
`hext_stream/trajectory/replay.py` — each guarding the same unimplemented
capability. RFC-HEXT016 §9 Rule 6 requires exactly one; both call sites now
import this one class instead of defining their own.
"""

from __future__ import annotations


class TheorySwitchingNotImplementedError(NotImplementedError):
    """RFC-HEXT016 §6.4: formula-plugin theory execution is not
    implemented. RC1 supports parameter-only theory switching (RFC-HEXT016
    §3-6, later milestones); this error is raised only for the still-
    unimplemented formula-plugin case, not for parameter-only theories."""
