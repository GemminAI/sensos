"""semantic.metric(vector + Gain) → controller.command.

Emits a `controller.command` object only. Does NOT control LLMs, does NOT
modify sampling temperature, does NOT call any API — enforcement is future,
out-of-scope work. `action` is a `ControllerAction` enum, not a free string,
so future actions (Reroute, Pause, Replay, Checkpoint) can be added without
breaking this ABI.

Thresholds below are an EXP-4010 policy choice, not spec-mandated (the spec
only defines the G formula, not discrete action bands).

RFC-HEXT016 §5.4/§6: both thresholds are now theory-overridable via an
injected `TheoryContext`, resolved through new keyword parameters on
`gain_to_action` — the decision logic itself (the four-branch cascade) is
unchanged.
"""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject
from hext_stream.schema.semantic import ControllerAction
from hext_stream.theory.context import TheoryContext

ALLOW_THRESHOLD = 0.9
WARN_THRESHOLD = 0.5


def gain_to_action(
    gain: float,
    lcf: float,
    *,
    allow_threshold: float = ALLOW_THRESHOLD,
    warn_threshold: float = WARN_THRESHOLD,
) -> ControllerAction:
    if lcf < 1.0:
        return ControllerAction.HARD_LOCK
    if gain >= allow_threshold:
        return ControllerAction.ALLOW
    if gain >= warn_threshold:
        return ControllerAction.WARN
    return ControllerAction.SOFT_LIMIT


class ControllerProcessor(HEXTProcessor):
    processor_type = "semantic.controller"
    version = "1.0.0"
    consumes = ["semantic.metric"]
    produces = ["controller.command"]

    def __init__(self, theory_context: TheoryContext | None = None) -> None:
        super().__init__()
        self._theory_context = theory_context or TheoryContext.default()

    def process(self, event: HextObject) -> list[HextObject]:
        metrics = event.payload.get("metrics", {})
        if "Gain" not in metrics:
            return []

        action = gain_to_action(
            metrics["Gain"],
            metrics.get("LCF", 0.0),
            allow_threshold=self._theory_context.coefficient("controller", "allow_threshold", ALLOW_THRESHOLD),
            warn_threshold=self._theory_context.coefficient("controller", "warn_threshold", WARN_THRESHOLD),
        )

        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="controller.command",
                parent=event,
                payload={
                    "action": action.value,
                    "gain": metrics["Gain"],
                    "trajectory_id": event.payload.get("trajectory_id", event.id),
                    "instruction_id": event.payload.get("instruction_id"),
                },
                metadata={"action": action.value},
            )
        ]
