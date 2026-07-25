"""RFC-HEXT014 §8: Telemetry API — the single read path for consumers.

[RFC-HEXT015] (Trajectory Runtime), [RFC-HEXT008] (DevTools / HEXT
Inspector), and any future consumer MUST reach telemetry only through this
class, never by holding a reference to the Execution Kernel, a Stream
Runtime adapter, or the Processor Registry directly (§8 Rule 1).
"""

from __future__ import annotations

from typing import Any

from hext_stream.schema.base import HextObject
from hext_stream.telemetry.aggregator import MetricEntry
from hext_stream.telemetry.runtime import TelemetryRuntime


class TelemetryAPI:
    """RFC-HEXT014 §8: read-only facade (§8 Rule 2) over a TelemetryRuntime."""

    def __init__(self, telemetry_runtime: TelemetryRuntime) -> None:
        self._telemetry = telemetry_runtime

    def health(self) -> dict[str, Any]:
        """RFC-HEXT014 §6: the current Runtime Health Monitor snapshot."""
        return self._telemetry.health_monitor.snapshot()

    def trajectories(self) -> list[str]:
        """Every `trajectory_id` the Metric Aggregator has recorded a metric for."""
        return self._telemetry.aggregator.trajectories()

    def metric_series(
        self, trajectory_id: str, metric_name: str, theory_id: str | None = None
    ) -> list[MetricEntry]:
        """RFC-HEXT014 §5: the immutable time series for one
        (trajectory, metric, theory) — `theory_id=None` (the default)
        selects the baseline, non-theory-swapped series."""
        return self._telemetry.aggregator.series(trajectory_id, metric_name, theory_id)

    def latest_metric(
        self, trajectory_id: str, metric_name: str, theory_id: str | None = None
    ) -> MetricEntry | None:
        return self._telemetry.aggregator.latest(trajectory_id, metric_name, theory_id)

    def theories_for(self, trajectory_id: str, metric_name: str) -> list[str | None]:
        """Every `theory_id` (including `None`, the baseline) with a
        recorded series for this (trajectory, metric) — RFC-HEXT016 §8's
        Theory Diff enumerates this before comparing two of them."""
        return self._telemetry.aggregator.theories_for(trajectory_id, metric_name)

    def event_log(self, *, limit: int = 1000) -> list[HextObject]:
        """RFC-HEXT008 §2.1 (Task 1) / §2's Task 2: raw telemetry event
        history — `processor.started`/`completed`/`failed`, `runtime.state`,
        and any `semantic.metric`/`controller.command` events a caller
        chose to also publish to the telemetry topic."""
        return self._telemetry.event_log(limit=limit)
