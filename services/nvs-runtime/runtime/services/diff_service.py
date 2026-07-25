"""State diff service — narrative and tag changes vs previous state."""

from __future__ import annotations

import difflib
import re
from typing import Any

from sqlalchemy.orm import Session

from runtime.core.exceptions import NotFoundError
from runtime.services.crystallizer import diffusion_display_label, schema_display_version
from runtime.services.state_service import StateService

T09_AXES = ["security", "economy", "technology", "resources", "ideology", "environment"]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def narrative_word_diff(before: str, after: str) -> dict[str, list]:
    prev_words = _tokenize(before)
    curr_words = _tokenize(after)
    matcher = difflib.SequenceMatcher(None, prev_words, curr_words)

    added: list[str] = []
    removed: list[str] = []
    changed: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            added.extend(curr_words[j1:j2])
        elif tag == "delete":
            removed.extend(prev_words[i1:i2])
        elif tag == "replace":
            before_chunk = " ".join(prev_words[i1:i2])
            after_chunk = " ".join(curr_words[j1:j2])
            changed.append(f"{before_chunk} → {after_chunk}")

    return {"added": added, "removed": removed, "changed": changed}


def t09_from_tags(tags: dict[str, Any]) -> dict[str, float]:
    raw = tags.get("T09") or tags.get("T09_strategic_interest_vector") or {}
    if isinstance(raw, list) and len(raw) == 6:
        return {ax: float(raw[i]) for i, ax in enumerate(T09_AXES)}
    if isinstance(raw, dict):
        return {ax: float(raw.get(ax, 0.0)) for ax in T09_AXES}
    return {ax: 0.0 for ax in T09_AXES}


def t22_label(state_row) -> str:
    return diffusion_display_label(state_row.epistemic_diffusion_state)


class DiffService:
    def __init__(self, state_service: StateService | None = None):
        self.state_service = state_service or StateService()

    def compute_diff(self, db: Session, state_hash: str) -> dict[str, Any]:
        current = self.state_service.get_state(db, state_hash)
        previous_hash, _ = self.state_service.get_neighbors(db, state_hash)

        if not previous_hash:
            raise NotFoundError("no_previous_state", f"No previous state for {state_hash}")

        previous = self.state_service.get_state(db, previous_hash)

        narrative = narrative_word_diff(previous.narrative, current.narrative)
        tags = {
            "T09": {
                "before": t09_from_tags(previous.tags),
                "after": t09_from_tags(current.tags),
            },
            "T22": {
                "before": t22_label(previous),
                "after": t22_label(current),
            },
            "schema_version": {
                "before": schema_display_version(previous.schema_version),
                "after": schema_display_version(current.schema_version),
            },
        }

        return {
            "current_hash": state_hash,
            "previous_hash": previous_hash,
            "narrative": narrative,
            "tags": tags,
        }
