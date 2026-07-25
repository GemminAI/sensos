"""T09 visualization utilities for Narrative Spectrometer (RC-2D)."""

from __future__ import annotations

import math
from typing import Any

T09_AXES = ["security", "economy", "technology", "resources", "ideology", "environment"]

T09_AXIS_LABELS = {
    "security": "Security",
    "economy": "Economy",
    "technology": "Technology",
    "resources": "Resource",
    "ideology": "Ideology",
    "environment": "Environment",
}


def t09_vector_from_dict(t09: dict[str, Any]) -> list[float]:
    return [float(t09.get(ax, 0.0)) for ax in T09_AXES]


def dominant_axis(t09: dict[str, Any]) -> str:
    vec = t09_vector_from_dict(t09)
    idx = max(range(len(vec)), key=lambda i: abs(vec[i]))
    return T09_AXES[idx]


def dominant_axis_label(t09: dict[str, Any]) -> str:
    return T09_AXIS_LABELS[dominant_axis(t09)]


def euclidean_distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    va = t09_vector_from_dict(a)
    vb = t09_vector_from_dict(b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(va, vb, strict=True)))


def pairwise_distances(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """states items must have 'origin' and 't09' keys."""
    rows: list[dict[str, Any]] = []
    for i, a in enumerate(states):
        for b in states[i + 1 :]:
            dist = euclidean_distance(a["t09"], b["t09"])
            oa = str(a["origin"]).upper()
            ob = str(b["origin"]).upper()
            rows.append(
                {
                    "pair": f"{oa} ↔ {ob}",
                    "origin_a": oa,
                    "origin_b": ob,
                    "distance": round(dist, 2),
                }
            )
    rows.sort(key=lambda r: r["distance"])
    return rows


def orientation_summary(states: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for state in sorted(states, key=lambda s: str(s["origin"])):
        origin = str(state["origin"]).upper()
        axis = dominant_axis_label(state["t09"])
        lines.append(f"{origin} emphasizes {axis}.")
    return lines
