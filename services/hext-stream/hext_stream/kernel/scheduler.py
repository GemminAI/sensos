"""RFC-HEXT011 §3: Runtime Scheduler.

The reference runtime's existing publish path is already synchronous and
single-threaded per topic (``StreamRuntime.publish`` -> ``backend.publish``),
which trivially satisfies §3 Rule 1's per-stream ordering requirement — see
§4.5's "minimal conformant implementation" allowance, cited by analogy here.

Per RFC-HEXT011 §6.1, this module does not keep its own record of
per-stream sequence progress — an earlier version did (a
``dict[str, int]`` tracking "last admitted sequence"), duplicating the
Sequence Allocator's own counters ([RFC-HEXT013] §5.2) and risking drift
between the two. ``admit`` now verifies against the Kernel Context's
``last_sequence`` (§6.2 Rule 2), the one place that fact is stored.
"""

from __future__ import annotations

from hext_stream.kernel.context import KernelContext


class SchedulerOrderViolation(Exception):
    """RFC-HEXT011 §3 Rule 1 violated — an admission disagreed with the
    Kernel Context's authoritative last-allocated sequence for the stream.

    Distinct from RFC-HEXT011 §8's ``KERNEL_ERR_SCHEDULER_STALL`` (a
    liveness/timeout failure, not implemented in Phase 1 — see the Phase 1
    report): this is a new, more specific code for the ordering-invariant
    check this module actually performs.
    """

    code = "KERNEL_ERR_SEQUENCE_VIOLATION"


class RuntimeScheduler:
    """RFC-HEXT011 §3: verifies per-stream non-decreasing admission order
    against the shared Kernel Context, rather than an independent record.
    """

    def __init__(self, context: KernelContext) -> None:
        self._context = context

    def admit(self, stream: str, sequence: int) -> None:
        """Record an admission and assert §3 Rule 1's ordering invariant
        against ``KernelContext.last_sequence`` (§6.2 Rule 2).

        Raises ``SchedulerOrderViolation`` if ``sequence`` does not match
        what the Kernel Context currently considers the most recently
        allocated sequence for this stream — i.e. never silently accepts
        an admission inconsistent with the single authoritative source.
        """
        authoritative = self._context.last_sequence(stream)
        if authoritative is None or sequence != authoritative:
            raise SchedulerOrderViolation(
                f"stream {stream!r}: admitted sequence {sequence} does not match "
                f"Kernel Context's last_sequence={authoritative!r}"
            )

    def last_admitted(self, stream: str) -> int | None:
        return self._context.last_sequence(stream)
