"""RFC-HEXT008 §3.3 (Task 3): Semantic Oscilloscope.

Six tracks — SED, OI, IF, LCF, Gain (from the Metric Aggregator,
RFC-HEXT014 §5, via `TelemetryAPI.metric_series`) and Runtime State (from
`runtime.state` telemetry events) — all addressed by the same shared
Replay Clock (`metadata.sequence`), per RFC-HEXT008 §3.3's Phase 3
amendment. No metric is computed here; every value is read from an
already-published event.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hext_stream.telemetry.api import TelemetryAPI

REQUIRED_METRIC_TRACKS = ("SED", "OI", "IF", "LCF", "Gain")


@dataclass(frozen=True)
class TrackPoint:
    sequence: int | None
    value: Any


@dataclass(frozen=True)
class OscilloscopeTrack:
    name: str
    points: list[TrackPoint]


class Oscilloscope:
    """RFC-HEXT008 §3.3 / Task 3: synchronized telemetry tracks sharing
    one replay clock (`metadata.sequence`)."""

    def __init__(self, telemetry: TelemetryAPI) -> None:
        self._telemetry = telemetry

    def metric_track(
        self, trajectory_id: str, metric_name: str, theory_id: str | None = None
    ) -> OscilloscopeTrack:
        """`theory_id=None` (the default) is the baseline track. RFC-HEXT016
        §8 Theory Diff overlays a second call with an alternate `theory_id`."""
        entries = self._telemetry.metric_series(trajectory_id, metric_name, theory_id)
        return OscilloscopeTrack(
            name=metric_name,
            points=[TrackPoint(sequence=e.sequence, value=e.value) for e in entries],
        )

    def runtime_state_track(self, *, limit: int = 1000) -> OscilloscopeTrack:
        events = [e for e in self._telemetry.event_log(limit=limit) if e.type == "runtime.state"]
        return OscilloscopeTrack(
            name="Runtime State",
            points=[
                TrackPoint(sequence=e.metadata.get("sequence"), value=e.payload["state"])
                for e in events
            ],
        )

    def snapshot(
        self, trajectory_id: str, *, theory_id: str | None = None, limit: int = 1000
    ) -> dict[str, OscilloscopeTrack]:
        """RFC-HEXT008 §3.3: all six required tracks for one trajectory,
        addressed by the same shared clock. `Runtime State` is
        theory-agnostic (kernel lifecycle, not a semantic metric) and is
        always the baseline regardless of `theory_id`."""
        tracks = {
            name: self.metric_track(trajectory_id, name, theory_id) for name in REQUIRED_METRIC_TRACKS
        }
        tracks["Runtime State"] = self.runtime_state_track(limit=limit)
        return tracks

    def seek(self, tracks: dict[str, OscilloscopeTrack], sequence: int) -> dict[str, Any]:
        """RFC-HEXT008 §3.3's "click any timecode seeks all tracks
        together": the value each track held at or immediately before
        `sequence` on the shared clock."""
        result: dict[str, Any] = {}
        for name, track in tracks.items():
            candidates = [p for p in track.points if p.sequence is not None and p.sequence <= sequence]
            result[name] = candidates[-1].value if candidates else None
        return result
