"""Origin comparison — group narrative states by event (same article)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from runtime.core.exceptions import NotFoundError
from runtime.db.tables import NarrativeState
from runtime.services.crystallizer import derive_event_id, diffusion_display_label
from runtime.services.diff_service import t09_from_tags

SUPPORTED_ORIGINS = {"jp", "us", "cn", "eu", "uk", "qa"}


def _event_key(row: NarrativeState) -> str:
    return row.event_id or derive_event_id(row.article)


class ComparisonService:
    def _all_rows(self, db: Session) -> list[NarrativeState]:
        return db.query(NarrativeState).order_by(NarrativeState.created_at.desc()).all()

    def _group_by_event(self, rows: list[NarrativeState]) -> dict[str, list[NarrativeState]]:
        groups: dict[str, list[NarrativeState]] = defaultdict(list)
        for row in rows:
            groups[_event_key(row)].append(row)
        return groups

    def list_events(self, db: Session) -> list[dict[str, Any]]:
        groups = self._group_by_event(self._all_rows(db))
        events = []
        for event_id, states in groups.items():
            origins = sorted({s.subject_origin for s in states})
            latest = max(s.created_at for s in states)
            events.append(
                {
                    "event_id": event_id,
                    "state_count": len(states),
                    "origins": origins,
                    "latest_created_at": latest.isoformat(),
                }
            )
        events.sort(key=lambda e: e["latest_created_at"], reverse=True)
        return events

    def compare(
        self,
        db: Session,
        event_id: str,
        origins: list[str] | None = None,
    ) -> dict[str, Any]:
        groups = self._group_by_event(self._all_rows(db))
        states = groups.get(event_id)
        if not states:
            raise NotFoundError("event_not_found", f"Event not found: {event_id}")

        origin_filter = None
        if origins:
            origin_filter = {o.strip().lower() for o in origins if o.strip().lower() in SUPPORTED_ORIGINS}

        by_origin: dict[str, NarrativeState] = {}
        for row in sorted(states, key=lambda s: s.created_at, reverse=True):
            if row.subject_origin in by_origin:
                continue
            if origin_filter and row.subject_origin not in origin_filter:
                continue
            by_origin[row.subject_origin] = row

        if not by_origin:
            raise NotFoundError("no_states_for_filter", f"No states for event {event_id} with given origins")

        ordered = [by_origin[k] for k in sorted(by_origin.keys())]
        return {
            "event_id": event_id,
            "states": [_state_compare_item(s) for s in ordered],
        }


def _state_compare_item(row: NarrativeState) -> dict[str, Any]:
    return {
        "origin": row.subject_origin,
        "state_hash": row.state_hash,
        "narrative": row.narrative,
        "tags": row.tags,
        "epistemic_diffusion_state": diffusion_display_label(row.epistemic_diffusion_state),
        "narrative_length": len(row.narrative),
        "t09": t09_from_tags(row.tags),
    }
