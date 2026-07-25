"""RFC-HEXT014 §5: Metric Aggregator.

Consumes already-produced `semantic.metric` events (§3.4) and builds an
immutable, append-only time series per (trajectory_id, metric_name,
theory_id). Never computes SED/OI/LCF/IF/Gain itself — every value comes
from `payload.metrics`, produced once by the EXP-4010 processor chain (or,
for a theory-swapped run, by RFC-HEXT016 §6's Theory Executor).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime

from hext_stream.schema.base import HextObject

SeriesKey = tuple[str, str, "str | None"]


@dataclass(frozen=True)
class MetricEntry:
    value: float
    object_id: str
    sequence: int | None
    timestamp: datetime


class MetricAggregator:
    """RFC-HEXT014 §5: immutable per-(trajectory, metric, theory) time series.

    RC1 amendment: the key gained a third component, `theory_id`. Under the
    prior two-part key, two different theories producing the same numeric
    value for a metric would have silently collapsed into one entry —
    exactly what Theory Diff (RFC-HEXT016 §8) needs to be able to tell
    apart. `theory_id=None` is the baseline (non-theory-swapped) case,
    unchanged in behavior from before this amendment.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._series: dict[SeriesKey, list[MetricEntry]] = {}

    def record(self, event: HextObject) -> None:
        """§5 Rule 1: read-only consumption of an already-computed
        `semantic.metric` event. §5 Rule 2: does not duplicate an entry
        whose value is unchanged from the last recorded value for the same
        (trajectory_id, metric_name, theory_id) — this is what makes a
        processor re-emission that carries forward unchanged metrics (e.g.
        the Gain Scheduler re-publishing SED/OI/LCF/IF unchanged alongside
        a new Gain value) append only the genuinely new point, without
        conflating results computed under different theories.
        """
        if event.type != "semantic.metric":
            return
        metrics = event.payload.get("metrics", {})
        trajectory_id = event.payload.get("trajectory_id", event.id)
        theory_id = event.payload.get("theory_id")
        sequence = event.metadata.get("sequence")
        with self._lock:
            for name, value in metrics.items():
                key: SeriesKey = (trajectory_id, name, theory_id)
                existing = self._series.setdefault(key, [])
                if existing and existing[-1].value == value:
                    continue
                existing.append(
                    MetricEntry(value=value, object_id=event.id, sequence=sequence, timestamp=event.timestamp)
                )

    def series(self, trajectory_id: str, metric_name: str, theory_id: str | None = None) -> list[MetricEntry]:
        """§5 Rule 3: entries orderable by `metadata.sequence`; insertion
        order already satisfies this since `record` is called in the same
        per-stream order the Runtime Scheduler admits objects in.
        `theory_id=None` (the default) selects the baseline series."""
        with self._lock:
            return list(self._series.get((trajectory_id, metric_name, theory_id), []))

    def trajectories(self) -> list[str]:
        with self._lock:
            return sorted({trajectory_id for trajectory_id, _, _ in self._series})

    def theories_for(self, trajectory_id: str, metric_name: str) -> list[str | None]:
        """Every `theory_id` (including `None`, the baseline) a series
        exists for, given a trajectory and metric — the enumeration
        Theory Diff needs before it can compare two of them."""
        with self._lock:
            return [
                theory_id
                for (tid, name, theory_id) in self._series
                if tid == trajectory_id and name == metric_name
            ]

    def latest(self, trajectory_id: str, metric_name: str, theory_id: str | None = None) -> MetricEntry | None:
        series = self.series(trajectory_id, metric_name, theory_id)
        return series[-1] if series else None
