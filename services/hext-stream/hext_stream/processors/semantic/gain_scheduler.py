"""semantic.metric(vector) → semantic.metric(vector + Gain).

EXP-4010 §5.1: G = exp(-alpha * SED) * floor(LCF).

Pure function of the single incoming metric-vector event — no process-memory
cache. Gain has no state beyond the published/replayable HEXT objects
themselves, so `runtime.replay()` reconstructs Gain history deterministically.

RFC-HEXT016 §5.4/§6: `alpha` is now theory-overridable via an injected
`TheoryContext`, resolved through the same `compute_gain(..., alpha=...)`
keyword this module already exposed — the formula itself is unchanged.
"""

from __future__ import annotations

import math

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject
from hext_stream.theory.context import TheoryContext

ALPHA = 0.1  # EXP-4010-local sensitivity constant; spec only requires alpha > 0.


def compute_gain(sed: float, lcf: float, *, alpha: float = ALPHA) -> float:
    floor_lcf = 1.0 if lcf >= 1.0 else 0.0
    return math.exp(-alpha * sed) * floor_lcf


class GainScheduler(HEXTProcessor):
    processor_type = "semantic.gain_scheduler"
    version = "1.0.0"
    consumes = ["semantic.metric"]
    produces = ["semantic.metric"]

    def __init__(self, theory_context: TheoryContext | None = None) -> None:
        super().__init__()
        # RFC-HEXT016 §5.4 Rule 1: None resolves to the baseline here,
        # once, so every use below is a single, uniform code path.
        self._theory_context = theory_context or TheoryContext.default()

    def process(self, event: HextObject) -> list[HextObject]:
        metrics = event.payload.get("metrics", {})
        if "SED" not in metrics or "LCF" not in metrics or "Gain" in metrics:
            return []

        alpha = self._theory_context.coefficient("gain", "alpha", ALPHA)
        gain = compute_gain(metrics["SED"], metrics["LCF"], alpha=alpha)

        payload = dict(event.payload)
        payload["metrics"] = dict(metrics)
        payload["metrics"]["Gain"] = gain

        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="semantic.metric",
                parent=event,
                payload=payload,
                metadata={"trajectory_id": event.payload.get("trajectory_id", event.id)},
            )
        ]
