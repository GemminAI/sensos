"""ASSERT-07: Idempotent Replay Conformance (CTS-21.7)."""

from __future__ import annotations

import math
from typing import Any

from hext_stream.schema.base import HextObject


def _metrics_from(events: list[HextObject]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for e in events:
        if e.type == "semantic.metric" and "SED" in e.payload.get("metrics", {}):
            metrics = e.payload["metrics"]
    return {k: metrics.get(k, float("nan")) for k in ("SED", "OI", "IF", "LCF")}


def extract(runtime, topic: str) -> tuple[dict[str, float], dict[str, float]]:
    from hext_stream.schema.replay import ReplayMode, ReplayRequest

    def replay_once() -> list[HextObject]:
        return runtime.replay(ReplayRequest(topic=topic, mode=ReplayMode.LAST_N, last_n=500))

    metrics_run1 = _metrics_from(replay_once())
    metrics_run2 = _metrics_from(replay_once())
    return metrics_run1, metrics_run2


def verify(metrics_run1: dict[str, float], metrics_run2: dict[str, float], case_id: str) -> tuple[bool, str]:
    """Ported verbatim from CTS-21.md §5 verify_assert_07_idempotent_replay."""
    for key in ("SED", "OI", "IF", "LCF"):
        if not math.isclose(metrics_run1[key], metrics_run2[key], abs_tol=1e-7):
            return False, (
                f"[FAIL] ASSERT-07: Metric drift in {key} for {case_id}. "
                f"Run1: {metrics_run1[key]}, Run2: {metrics_run2[key]}"
            )
    return True, "[PASS] ASSERT-07: Idempotent replay metrics verified."
