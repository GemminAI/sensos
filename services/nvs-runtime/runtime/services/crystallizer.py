"""35TAG state_hash crystallization (35TAG v6.0 RC-1 subset)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = "35tag.v6.0.rc1"


def compute_epistemic_diffusion_state(tags: dict[str, Any]) -> str:
    t19 = float(tags.get("T19", tags.get("T19_conflict_factuality_index", 0.0)))
    t10 = float(tags.get("T10", tags.get("T10_epistemic_confidence", 0.5)))
    if t19 >= 0.6:
        return "high_conflict"
    if t10 < 0.4:
        return "low_confidence"
    if t19 >= 0.3:
        return "diffuse"
    return "stable"


def crystallize_state_hash(narrative: str, tags: dict[str, Any], origin: str) -> str:
    """SHA-256 over canonical JCS-like payload (narrative + tags + origin)."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "subject_origin": origin,
        "narrative": narrative.strip(),
        "tags": tags,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


DIFFUSION_LABELS: dict[str, str] = {
    "stable": "Crystallized",
    "diffuse": "Diffused",
    "low_confidence": "Diffused",
    "high_conflict": "Polarized",
}


def diffusion_display_label(internal: str) -> str:
    return DIFFUSION_LABELS.get(internal, internal.title())


def schema_display_version(stored: str) -> str:
    if stored.startswith("35tag.v6"):
        return "6.0.0"
    return stored


def derive_event_id(article: str) -> str:
    """Stable event id from article content (same article → same event)."""
    digest = hashlib.sha256(article.strip().encode("utf-8")).hexdigest()[:12]
    return f"evt-{digest}"

