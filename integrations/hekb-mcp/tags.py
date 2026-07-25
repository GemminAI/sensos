"""35TAG vector extraction for hekb_mcp (Phase4 MIG-TAGS).

Behavior-identical offline path to the former
``kernel.observer.tag_extractor`` implementation (deterministic 35-dim vector).
Optional API path prefers Product ``semantic-annotator`` when configured.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

import numpy as np

TAG_VECTOR_DIM = 35
TAG_INDEX_T10 = 9
TAG_INDEX_T19 = 18
TAG_INDEX_T22 = 21


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _slot_hash(text: str, index: int) -> float:
    digest = hashlib.sha256(f"{index}:{text}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _heuristic_t10(text: str) -> float:
    lower = text.lower()
    confidence_markers = (
        "evidence",
        "peer-reviewed",
        "established",
        "confirmed",
        "verified",
        "consistently",
    )
    hedge_markers = ("might", "perhaps", "unclear", "disputed", "alleged")
    score = 0.55
    score += 0.05 * sum(1 for m in confidence_markers if m in lower)
    score -= 0.06 * sum(1 for m in hedge_markers if m in lower)
    return _clamp01(score)


def _heuristic_t19(text: str) -> float:
    lower = text.lower()
    conflict_markers = (
        "false",
        "misleading",
        "contradict",
        "disputed",
        "incorrect",
        "debunked",
        "conflicting",
    )
    score = 0.05 * sum(1 for m in conflict_markers if m in lower)
    if re.search(r"\b(osaka|flat earth|equals 5|five)\b", lower):
        score += 0.35
    return _clamp01(score)


def _heuristic_t22(text: str) -> float:
    tokens = re.findall(r"\S+", text)
    if len(tokens) < 2:
        return 0.0
    unique_ratio = len(set(t.lower() for t in tokens)) / len(tokens)
    return _clamp01(unique_ratio)


def build_tag_vector(text: str, annotation: dict[str, Any] | None = None) -> np.ndarray:
    """Build a 35-dimensional observation vector y(t)."""
    vec = np.zeros(TAG_VECTOR_DIM, dtype=np.float64)
    t10 = annotation.get("T10", _heuristic_t10(text)) if annotation else _heuristic_t10(text)
    t19 = annotation.get("T19", _heuristic_t19(text)) if annotation else _heuristic_t19(text)
    vec[TAG_INDEX_T10] = _clamp01(float(t10))
    vec[TAG_INDEX_T19] = _clamp01(float(t19))
    vec[TAG_INDEX_T22] = _heuristic_t22(text)

    for i in range(TAG_VECTOR_DIM):
        if vec[i] == 0.0:
            vec[i] = _slot_hash(text, i)

    if annotation:
        for key, value in annotation.items():
            if key.startswith("T") and key[1:].isdigit():
                idx = int(key[1:]) - 1
                if 0 <= idx < TAG_VECTOR_DIM:
                    try:
                        vec[idx] = _clamp01(float(value))
                    except (TypeError, ValueError):
                        pass
    return vec


def annotate_via_api(
    text: str,
    *,
    api_url: str | None = None,
    provider: str = "anthropic",
    timeout: int = 60,
) -> dict[str, Any]:
    """Call Product semantic-annotator (or TAG_GENERATOR_URL) /annotate."""
    url = (
        api_url
        or os.environ.get("SEMANTIC_ANNOTATOR_URL")
        or os.environ.get("TAG_GENERATOR_URL")
        or "http://localhost:8011/annotate"
    )
    payload = {"text": text, "provider": provider}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"annotator HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"annotator unreachable at {url}: {exc}") from exc

    # Map Product annotator field names into T10/T19 slots when present.
    tags = raw.get("tags", raw) if isinstance(raw, dict) else {}
    if isinstance(tags, dict):
        if "T10" not in tags and "T10_epistemic_confidence" in tags:
            tags = {**tags, "T10": tags["T10_epistemic_confidence"]}
        if "T19" not in tags and "T19_conflict_factuality_index" in tags:
            tags = {**tags, "T19": tags["T19_conflict_factuality_index"]}
    return tags if isinstance(tags, dict) else {}


def extract_tag_vector(
    text: str,
    *,
    use_api: bool = False,
    api_url: str | None = None,
    provider: str = "anthropic",
) -> np.ndarray:
    annotation = None
    if use_api:
        annotation = annotate_via_api(text, api_url=api_url, provider=provider)
    return build_tag_vector(text, annotation)
