"""RFC-HEXT015 §3 (Task 7): Replay Engine Integration.

Orchestrates the existing `ReplayEngine` (`runtime/replay.py`, untouched)
rather than replacing it: `from_timestamp`/`last_n` delegate directly to
`ReplayEngine.replay_from_timestamp`/`.replay_last_n`; `from_sequence` is
orchestrated over the existing History interface instead, per this
document's Phase 3 amendment note (the reference engine's `FROM_ID` mode
is keyed by a backend event id that cannot be derived from
`metadata.sequence` through any existing public API).

RC1 note (Milestone 5): `ReplayHandle.run(theory_context=...)` accepts a
resolved `TheoryContext` (RFC-HEXT016 §5.4) — never a raw `theory_id` or
`TheoryConfig` — and is now a thin orchestration layer over the Theory
Executor (RFC-HEXT016 §6.2, §7): it resolves `theory_context=None` to
`TheoryContext.default()` and, either way, delegates straight to
`TheoryExecutor.execute`, returning the one `TheoryResult` that call
produces wrapped in a `ReplayResult`. No independent deferral or
pass-through path remains here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from hext_stream.schema.base import HextObject
from hext_stream.theory.context import TheoryContext
from hext_stream.theory.executor import TheoryExecutor, TheoryResult

HistoryFn = Callable[..., list[HextObject]]
ReplayFromTimestampFn = Callable[[str, datetime], list[HextObject]]
ReplayLastNFn = Callable[[str, int], list[HextObject]]

_HISTORY_SCAN_LIMIT = 100_000


@dataclass(frozen=True)
class ReplayResult:
    """RFC-HEXT016 §7 (Milestone 5): wraps the one `TheoryResult` produced
    by `ReplayHandle.run`'s single `TheoryExecutor.execute` call."""

    theory_result: TheoryResult


class ReplayHandle:
    """RFC-HEXT015 §3: a resolved, ordered replay set, not yet "run"."""

    def __init__(self, objects: list[HextObject]) -> None:
        self._objects = objects

    def objects(self) -> list[HextObject]:
        return list(self._objects)

    def verify_digest_determinism(self, other: "ReplayHandle") -> bool:
        """RFC-HEXT015 §3 Rule 2: bit-for-bit determinism, verified via
        `metadata.payload_digest` ([RFC-HEXT013] §6) — not merely assumed."""
        mine = [o.metadata.get("payload_digest") for o in self._objects]
        theirs = [o.metadata.get("payload_digest") for o in other._objects]
        return mine == theirs

    def run(self, *, theory_context: TheoryContext | None = None) -> ReplayResult:
        """RFC-HEXT016 §7: thin orchestration over the Theory Executor.
        RFC-HEXT015 §3 Rule 4: does not mutate source history — the
        Executor's own §6 Rule 2 already guarantees this. RFC-HEXT016 §5.4
        Rule 1: `theory_context=None` and an explicit default context are
        indistinguishable — both resolve to the identical Executor call
        below."""
        context = theory_context if theory_context is not None else TheoryContext.default()
        theory_result = TheoryExecutor().execute(context, self.objects())
        return ReplayResult(theory_result=theory_result)


class ReplayOrchestrator:
    """RFC-HEXT015 §3 / Task 7: orchestrates replay; performs no transport
    of its own."""

    def __init__(
        self,
        *,
        history_fn: HistoryFn,
        replay_from_timestamp_fn: ReplayFromTimestampFn,
        replay_last_n_fn: ReplayLastNFn,
    ) -> None:
        self._history_fn = history_fn
        self._replay_from_timestamp_fn = replay_from_timestamp_fn
        self._replay_last_n_fn = replay_last_n_fn

    def from_sequence(self, stream: str, sequence: int) -> ReplayHandle:
        """History-orchestrated — see module docstring."""
        objects = [
            o for o in self._history_fn(stream, limit=_HISTORY_SCAN_LIMIT)
            if (s := o.metadata.get("sequence")) is not None and s >= sequence
        ]
        objects.sort(key=lambda o: o.metadata.get("sequence", 0))
        return ReplayHandle(objects)

    def from_timestamp(self, stream: str, timestamp: datetime) -> ReplayHandle:
        """Engine-native — delegates directly to `ReplayEngine.replay_from_timestamp`."""
        return ReplayHandle(self._replay_from_timestamp_fn(stream, timestamp))

    def last_n(self, stream: str, n: int) -> ReplayHandle:
        """Engine-native — delegates directly to `ReplayEngine.replay_last_n`."""
        return ReplayHandle(self._replay_last_n_fn(stream, n))
