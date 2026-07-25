"""Persistence layer for crystallized narrative states."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from runtime.core.exceptions import NotFoundError
from runtime.db.tables import NarrativeState
from runtime.services.crystallizer import derive_event_id, diffusion_display_label


class StateService:
    def create(
        self,
        db: Session,
        *,
        state_hash: str,
        narrative: str,
        tags: dict[str, Any],
        subject_origin: str,
        schema_version: str,
        epistemic_diffusion_state: str,
        article: str,
        provider: str,
        event_id: str | None = None,
    ) -> NarrativeState:
        existing = db.get(NarrativeState, state_hash)
        if existing:
            return existing

        row = NarrativeState(
            state_hash=state_hash,
            event_id=event_id or derive_event_id(article),
            narrative=narrative,
            tags=tags,
            subject_origin=subject_origin,
            schema_version=schema_version,
            epistemic_diffusion_state=epistemic_diffusion_state,
            article=article,
            provider=provider,
        )
        db.add(row)
        db.flush()
        db.refresh(row)
        return row

    def list_states(self, db: Session, limit: int = 50, offset: int = 0) -> list[NarrativeState]:
        return (
            db.query(NarrativeState)
            .order_by(NarrativeState.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def list_timeline(
        self,
        db: Session,
        *,
        limit: int = 100,
        origin: str | None = None,
    ) -> list[NarrativeState]:
        query = db.query(NarrativeState)
        if origin:
            query = query.filter(NarrativeState.subject_origin == origin.strip().lower())
        return query.order_by(NarrativeState.created_at.desc()).limit(limit).all()

    def get_neighbors(
        self,
        db: Session,
        state_hash: str,
        *,
        origin: str | None = None,
    ) -> tuple[str | None, str | None]:
        current = self.get_state(db, state_hash)
        query = db.query(NarrativeState)
        if origin:
            query = query.filter(NarrativeState.subject_origin == origin.strip().lower())
        else:
            query = query.filter(NarrativeState.subject_origin == current.subject_origin)

        rows = query.order_by(NarrativeState.created_at.desc()).all()
        hashes = [r.state_hash for r in rows]
        if state_hash not in hashes:
            return None, None

        idx = hashes.index(state_hash)
        # Timeline is newest-first: previous = older, next = newer
        previous = hashes[idx + 1] if idx + 1 < len(hashes) else None
        next_hash = hashes[idx - 1] if idx > 0 else None
        return previous, next_hash

    def get_state(self, db: Session, state_hash: str) -> NarrativeState:
        row = db.get(NarrativeState, state_hash)
        if not row:
            raise NotFoundError("state_not_found", f"State not found: {state_hash}")
        return row
