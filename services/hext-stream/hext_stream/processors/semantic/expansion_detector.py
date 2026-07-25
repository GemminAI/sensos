"""Diagram(stage=generated_category) → Expansion Candidate objects + Diagram(stage=expansion_summary).

Detects Obj(A) \\ i(Obj(R)) — nodes present in the generated implementation
that the required category never asked for — and publishes each as a
first-class `expansion.candidate` HextObject. Also emits one
`expansion_summary` diagram event carrying R, A, literals, generated text and
an initially-empty metrics vector, so downstream calculators (lcf/sed/oi/if)
can each merge their value into a single Metric Object instead of publishing
one object apiece.
"""

from __future__ import annotations

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject
from hext_stream.schema.semantic import ExpansionCandidatePayload, ExpansionCandidateType


class ExpansionDetector(HEXTProcessor):
    processor_type = "semantic.expansion_detector"
    version = "1.0.0"
    consumes = ["diagram"]
    produces = ["expansion.candidate", "diagram"]

    def process(self, event: HextObject) -> list[HextObject]:
        if event.metadata.get("stage") != "generated_category":
            return []

        required_objects = set(event.payload.get("required_graph", {}).get("objects", []))
        generated_objects = set(event.payload.get("generated_graph", {}).get("objects", []))
        excess = sorted(generated_objects - required_objects)

        instruction_id = event.payload.get("instruction_id", event.id)
        trajectory_id = event.payload.get("trajectory_id", event.id)
        candidate_labels = event.payload.get("candidate_labels", {})

        candidates: list[dict] = []
        outputs: list[HextObject] = []
        for node in excess:
            label = candidate_labels.get(node, ExpansionCandidateType.NEUTRAL.value)
            candidate_payload = ExpansionCandidatePayload(
                id=f"expcand:{trajectory_id}:{node}",
                instruction_id=instruction_id,
                trajectory_id=trajectory_id,
                candidate_type=ExpansionCandidateType(label),
                generated_node=node,
                required_node=None,
                processor=self.processor_type,
            )
            candidates.append(candidate_payload.model_dump(mode="json"))
            outputs.append(
                derive_event(
                    source=f"processor:{self.processor_type}",
                    event_type="expansion.candidate",
                    parent=event,
                    payload=candidate_payload.model_dump(mode="json"),
                    metadata={"trajectory_id": trajectory_id, "candidate_type": label},
                )
            )

        summary_payload = dict(event.payload)
        summary_payload["stage"] = "expansion_summary"
        summary_payload["candidates"] = candidates
        summary_payload["metrics"] = {}

        outputs.append(
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="diagram",
                parent=event,
                payload=summary_payload,
                metadata={"stage": "expansion_summary"},
            )
        )
        return outputs
