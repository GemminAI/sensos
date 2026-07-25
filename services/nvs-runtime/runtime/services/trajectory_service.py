"""Event trajectory — T09 projection and chronological state path."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from runtime.core.exceptions import NotFoundError
from runtime.db.tables import NarrativeState
from runtime.services.comparison_service import ComparisonService
from runtime.services.crystallizer import diffusion_display_label
from runtime.services.diff_service import t09_from_tags


def project_t09(t09: dict[str, Any]) -> tuple[float, float, float]:
    """Simple T09 axis-difference projection (no PCA/UMAP)."""
    x = float(t09.get("security", 0.0)) - float(t09.get("economy", 0.0))
    y = float(t09.get("technology", 0.0)) - float(t09.get("ideology", 0.0))
    z = float(t09.get("environment", 0.0)) - float(t09.get("resources", 0.0))
    return round(x, 2), round(y, 2), round(z, 2)


def trajectory_length(points: list[dict[str, Any]]) -> float:
    total = 0.0
    for i in range(1, len(points)):
        a, b = points[i - 1], points[i]
        dx = b["x"] - a["x"]
        dy = b["y"] - a["y"]
        dz = b["z"] - a["z"]
        total += math.sqrt(dx * dx + dy * dy + dz * dz)
    return round(total, 2)


def diffusion_changes(points: list[dict[str, Any]]) -> int:
    if len(points) < 2:
        return 0
    changes = 0
    for i in range(1, len(points)):
        if points[i]["diffusion"] != points[i - 1]["diffusion"]:
            changes += 1
    return changes


def duration_days(points: list[dict[str, Any]]) -> int:
    if len(points) < 2:
        return 0
    from datetime import datetime

    first = datetime.fromisoformat(points[0]["created_at"].replace("Z", "+00:00"))
    last = datetime.fromisoformat(points[-1]["created_at"].replace("Z", "+00:00"))
    return max(0, (last - first).days)


class TrajectoryService:
    def __init__(self, comparison_service: ComparisonService | None = None):
        self.comparison = comparison_service or ComparisonService()

    def _states_for_event(self, db: Session, event_id: str) -> list[NarrativeState]:
        groups = self.comparison._group_by_event(self.comparison._all_rows(db))
        states = groups.get(event_id)
        if not states:
            raise NotFoundError("event_not_found", f"Event not found: {event_id}")
        return sorted(states, key=lambda s: s.created_at)

    def get_trajectory(self, db: Session, event_id: str) -> dict[str, Any]:
        states = self._states_for_event(db, event_id)
        points = [_trajectory_point(row) for row in states]
        return {"event_id": event_id, "points": points}


def _trajectory_point(row: NarrativeState) -> dict[str, Any]:
    t09 = t09_from_tags(row.tags)
    x, y, z = project_t09(t09)
    return {
        "state_hash": row.state_hash,
        "created_at": row.created_at.isoformat(),
        "origin": row.subject_origin,
        "x": x,
        "y": y,
        "z": z,
        "diffusion": diffusion_display_label(row.epistemic_diffusion_state),
    }
