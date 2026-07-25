"""RFC-HEXT016 §6: Theory Executor (Parameter-Only).

Theory-scoped orchestration only. Reuses the existing `Pipeline`
(`hext_stream/processors/pipeline.py`, [RFC-HEXT004] §7's linear,
converging, multi-stage orchestrator already used by every CTS-21/22 case
run) instead of inventing a second pipeline mechanism. Does not accept or
produce a `SnapshotHandle`/`ReplayHandle` (§7 Theory Replay's job, a later
milestone) and does not publish to a live topic or touch a `StreamBackend`
(transport, out of scope here) — `execute`'s `Pipeline` is given a private,
in-memory, non-transport `publish_fn`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hext_stream.processors.pipeline import Pipeline
from hext_stream.schema.base import HextObject
from hext_stream.theory.context import TheoryContext

_ENTRY_TYPE = "observation"


@dataclass(frozen=True)
class TheoryResult:
    """RFC-HEXT016 §6.1. One complete execution of the parameterized
    EXP-4010 chain under a single `TheoryContext`. `metrics` and
    `controller_outputs` are convenience views over `events`, not a
    separate computation — every object in either also appears in
    `events`, in the same order."""

    theory_context: TheoryContext
    events: list[HextObject] = field(default_factory=list)
    metrics: list[HextObject] = field(default_factory=list)
    controller_outputs: list[HextObject] = field(default_factory=list)


class TheoryExecutor:
    """RFC-HEXT016 §6.2."""

    def execute(self, theory_context: TheoryContext | None, objects: list[HextObject]) -> TheoryResult:
        # Deferred: `processors.semantic`'s modules import `theory.context`,
        # which (via `hext_stream/theory/__init__.py`) imports this module —
        # a module-level import here would be circular. By call time, both
        # packages are already fully initialized.
        from hext_stream.processors.semantic import build_pipeline_processors

        context = theory_context if theory_context is not None else TheoryContext.default()

        captured: list[HextObject] = []

        def _capture(topic: str, event: HextObject) -> str:
            # RFC-HEXT016 §6.2 Rule 3: never StreamRuntime.publish / a
            # StreamBackend — this call touches no topic or transport.
            captured.append(event)
            return event.id

        pipeline = Pipeline(*build_pipeline_processors(context), publish_fn=_capture)

        for obj in objects:
            if obj.type != _ENTRY_TYPE:
                # §6.2 Rule 2: mixed Snapshot/Replay history the EXP-4010
                # chain does not itself consume is skipped, not rejected.
                continue
            pipeline.execute(obj.type, obj)

        events: list[HextObject] = []
        metrics: list[HextObject] = []
        controller_outputs: list[HextObject] = []
        for event in captured:
            if event.type == "semantic.metric":
                # §6 Rule 3: Executor-level tagging of its own freshly
                # derived output, via model_copy — never in-place mutation,
                # and never a change to any processor's own emitted payload.
                payload = dict(event.payload)
                payload["theory_id"] = context.theory_id
                event = event.model_copy(update={"payload": payload})
                metrics.append(event)
            elif event.type == "controller.command":
                controller_outputs.append(event)
            events.append(event)

        return TheoryResult(
            theory_context=context,
            events=events,
            metrics=metrics,
            controller_outputs=controller_outputs,
        )
