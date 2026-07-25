"""RFC-HEXT008 §3.5 (Task 5): Replay Controller — Play/Pause/Seek/Speed.

A transport-style controller over an ordered sequence of `HextObject`s.
Part A (this module) operates over `TelemetryAPI.event_log()`, since
Trajectory Runtime's richer Replay interface (RFC-HEXT015 §3) does not
exist until Part B, and the implementation order is intentionally
DevTools-then-Trajectory-Runtime. The `source` is injected as a callable
specifically so Part B can later supply a `TrajectoryManager`-backed
source without changing this class's public interface (RFC-HEXT008 §3.5's
"prepare extension points").

RC1 note (Milestone 6, final): `play(theory_context=...)` accepts a
resolved `TheoryContext` (RFC-HEXT016 §5.4) — never a raw `theory_id` or
`TheoryConfig`; a caller resolves via `TheoryManager.context_for(theory_id)`
first. Per RFC-HEXT016 §9 Rule 7 / TODO-016-02, `play` now routes through
the identical `ReplayHandle.run` path Trajectory Runtime's own replay uses
(RFC-HEXT016 §7) — no second execution mechanism: it wraps this
controller's already-loaded `self._events` in a `ReplayHandle` and
delegates. `hext_stream.theory.errors.TheorySwitchingNotImplementedError`
is no longer raised from this module (there is nothing left to defer).
"""

from __future__ import annotations

from typing import Callable

from hext_stream.schema.base import HextObject
from hext_stream.theory.context import TheoryContext
from hext_stream.trajectory.replay import ReplayHandle, ReplayResult

EventSource = Callable[[], list[HextObject]]


class ReplayController:
    """RFC-HEXT008 §3.5 / Task 5."""

    def __init__(self, source: EventSource) -> None:
        self._source_fn = source
        self._events: list[HextObject] = []
        self._position = 0
        self._playing = False
        self._speed = 1.0
        self._last_replay_result: ReplayResult | None = None

    def load(self) -> None:
        """Fetch (or refresh) the ordered event set this controller plays
        over. Does not mutate `source`'s underlying data — a pure read."""
        self._events = self._source_fn()
        self._position = 0

    def play(self, *, theory_context: TheoryContext | None = None) -> ReplayResult:
        """RFC-HEXT016 §7/§9 Rule 7 (TODO-016-02, resolved): the DevTools
        entry point over `ReplayHandle.run` — no execution path of its
        own. Wraps the already-loaded `self._events` in a `ReplayHandle`
        and delegates; `theory_context=None` and
        `theory_context=TheoryContext.default()` are indistinguishable in
        output, per §5.4 Rule 1, since both reach the identical call.
        The result is cached (`last_replay_result`) for callers — e.g. the
        Oscilloscope — that want it without re-running."""
        result = ReplayHandle(list(self._events)).run(theory_context=theory_context)
        self._last_replay_result = result
        self._playing = True
        return result

    @property
    def last_replay_result(self) -> ReplayResult | None:
        return self._last_replay_result

    def pause(self) -> None:
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing

    def seek(self, sequence: int) -> HextObject | None:
        """RFC-HEXT008 §3.5 Rule 2: jump directly to `sequence` on the
        shared Replay Clock, without iterating intermediate objects."""
        for index, event in enumerate(self._events):
            event_sequence = event.metadata.get("sequence")
            if event_sequence is not None and event_sequence >= sequence:
                self._position = index
                return event
        self._position = len(self._events)
        return None

    def set_speed(self, speed: float) -> None:
        """RFC-HEXT008 §3.5 Rule 3: display-pacing only — has no bearing
        on replay determinism, which concerns object order, not wall-clock
        pace."""
        if speed <= 0:
            raise ValueError("speed must be positive")
        self._speed = speed

    @property
    def speed(self) -> float:
        return self._speed

    def current(self) -> HextObject | None:
        if 0 <= self._position < len(self._events):
            return self._events[self._position]
        return None

    def step(self) -> HextObject | None:
        """Advance one position (only meaningful while playing) and
        return the newly current object, or None at end of stream."""
        if not self._playing or self._position >= len(self._events):
            return None
        event = self._events[self._position]
        self._position += 1
        return event
