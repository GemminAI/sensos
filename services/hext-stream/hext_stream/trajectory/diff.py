"""RFC-HEXT016 §8: Theory Diff (fulfills [RFC-HEXT008] §2.2).

Lives here, not in `hext_stream/theory/`, because this document's own
dependency direction (RFC-HEXT016 §1.1: Trajectory Runtime consumes Theory
Runtime, never the reverse) forbids `hext_stream/theory/` from importing a
Trajectory Runtime type such as `ReplayResult`.

A pure read-side comparison of two already-produced `ReplayResult`s — no
pipeline execution happens here. Both `TheoryResult`s being compared were
already produced by whichever two `ReplayHandle.run` calls the caller made.

RC1 note (Milestone 6, final): `TheoryDiff` gains three DevTools-ready
sub-objects — `ControllerDelta` (the full controller.command comparison,
not just the action string), `EventDelta` (per-event-type counts across
the two full pipeline runs), and `Summary` (a single rollup requiring no
further derivation from a DevTools panel). None of these require a second
comparison pass over `replay_a`/`replay_b` — `compare` computes them once,
from the same `TheoryResult`s already read for `metric_deltas`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hext_stream.schema.base import HextObject
from hext_stream.trajectory.replay import ReplayResult


def _final_metrics(metrics: list[HextObject]) -> dict[str, float]:
    """The last `semantic.metric` object's `payload["metrics"]` dict — the
    cumulative superset every EXP-4010 stage's payload already carries
    forward (RFC-HEXT016 §8), or `{}` if the run produced none. `metrics`
    is already `TheoryResult.metrics` — pre-filtered to `semantic.metric`
    objects by `TheoryExecutor` (RFC-HEXT016 §6.2)."""
    if not metrics:
        return {}
    return dict(metrics[-1].payload.get("metrics", {}))


def _final_command(controller_outputs: list[HextObject]) -> HextObject | None:
    """`controller_outputs` is already `TheoryResult.controller_outputs` —
    pre-filtered to `controller.command` objects."""
    return controller_outputs[-1] if controller_outputs else None


def _event_type_counts(events: list[HextObject]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        counts[event.type] = counts.get(event.type, 0) + 1
    return counts


@dataclass(frozen=True)
class MetricDelta:
    metric_name: str
    value_a: float | None
    value_b: float | None
    delta: float | None


@dataclass(frozen=True)
class ControllerDelta:
    """The full `controller.command` comparison — not just the action
    label, so a DevTools panel can also show the `gain` that produced it."""

    action_a: str | None
    action_b: str | None
    gain_a: float | None
    gain_b: float | None

    @property
    def action_changed(self) -> bool:
        return self.action_a != self.action_b

    @property
    def gain_delta(self) -> float | None:
        if isinstance(self.gain_a, (int, float)) and isinstance(self.gain_b, (int, float)):
            return self.gain_b - self.gain_a
        return None


@dataclass(frozen=True)
class EventDelta:
    """Per-event-type counts across each side's full `TheoryResult.events`
    — the structural layer of the comparison, complementing
    `metric_deltas`'/`ControllerDelta`'s semantic-value layer."""

    counts_a: dict[str, int]
    counts_b: dict[str, int]
    total_a: int
    total_b: int

    @property
    def count_delta(self) -> int:
        return self.total_b - self.total_a


@dataclass(frozen=True)
class Summary:
    """One DevTools-panel-ready rollup — every field here is already
    derived; a caller should not need to re-read `metric_deltas`,
    `controller_delta`, or `event_delta` to answer "did anything change,
    and what.\""""

    theory_id_a: str | None
    theory_id_b: str | None
    changed_metric_names: list[str]
    action_changed: bool
    event_count_delta: int


@dataclass(frozen=True)
class TheoryDiff:
    """RFC-HEXT016 §8. Compares two `ReplayResult`s — e.g. one run with
    `theory_context=None`, one with an alternate `TheoryContext` obtained
    from `TheoryManager.context_for(theory_id)` — never the execution
    pipeline itself."""

    replay_a: ReplayResult
    replay_b: ReplayResult
    metric_deltas: list[MetricDelta] = field(default_factory=list)
    controller_delta: ControllerDelta = field(
        default_factory=lambda: ControllerDelta(action_a=None, action_b=None, gain_a=None, gain_b=None)
    )
    event_delta: EventDelta = field(
        default_factory=lambda: EventDelta(counts_a={}, counts_b={}, total_a=0, total_b=0)
    )
    summary: Summary = field(
        default_factory=lambda: Summary(
            theory_id_a=None, theory_id_b=None, changed_metric_names=[], action_changed=False, event_count_delta=0
        )
    )

    @classmethod
    def compare(cls, replay_a: ReplayResult, replay_b: ReplayResult) -> "TheoryDiff":
        result_a, result_b = replay_a.theory_result, replay_b.theory_result

        metrics_a = _final_metrics(result_a.metrics)
        metrics_b = _final_metrics(result_b.metrics)
        deltas: list[MetricDelta] = []
        for name in sorted(set(metrics_a) | set(metrics_b)):
            value_a = metrics_a.get(name)
            value_b = metrics_b.get(name)
            delta = (
                value_b - value_a
                if isinstance(value_a, (int, float)) and isinstance(value_b, (int, float))
                else None
            )
            deltas.append(MetricDelta(metric_name=name, value_a=value_a, value_b=value_b, delta=delta))

        command_a = _final_command(result_a.controller_outputs)
        command_b = _final_command(result_b.controller_outputs)
        controller_delta = ControllerDelta(
            action_a=command_a.payload.get("action") if command_a else None,
            action_b=command_b.payload.get("action") if command_b else None,
            gain_a=command_a.payload.get("gain") if command_a else None,
            gain_b=command_b.payload.get("gain") if command_b else None,
        )

        event_delta = EventDelta(
            counts_a=_event_type_counts(result_a.events),
            counts_b=_event_type_counts(result_b.events),
            total_a=len(result_a.events),
            total_b=len(result_b.events),
        )

        summary = Summary(
            theory_id_a=result_a.theory_context.theory_id,
            theory_id_b=result_b.theory_context.theory_id,
            changed_metric_names=[d.metric_name for d in deltas if d.value_a != d.value_b],
            action_changed=controller_delta.action_changed,
            event_count_delta=event_delta.count_delta,
        )

        return cls(
            replay_a=replay_a,
            replay_b=replay_b,
            metric_deltas=deltas,
            controller_delta=controller_delta,
            event_delta=event_delta,
            summary=summary,
        )
