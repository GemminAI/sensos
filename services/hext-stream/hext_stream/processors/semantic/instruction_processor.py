"""Observation (instruction) → Diagram(stage=instruction) — EXP-4010 entry stage.

Extracts L_given (literal constraints) deterministically. Does NOT infer the
Required Category R — R is a fixed, human-authored gold standard supplied in
the seed event's payload (per EXP-4010 spec §4.1) and only carried forward.
"""

from __future__ import annotations

import re

from hext_stream.processors.base import HEXTProcessor, derive_event
from hext_stream.schema.base import HextObject

_PATTERNS = {
    "absolute_path": re.compile(r"(?<![\w./])/[\w\-./]+"),
    "uuid": re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    ),
    "rfc_id": re.compile(r"\bRFC-[A-Z0-9]+(?:-[A-Z0-9]+)*\b"),
    "hext_id": re.compile(r"\bhext:[\w:\-]+\b"),
    "quoted_string": re.compile(r"\"[^\"]+\"|'[^']+'|`[^`]+`"),
}


def extract_literals(text: str) -> list[str]:
    """Deterministic literal extraction — regex only, no AI interpretation."""
    found: list[str] = []
    for pattern in _PATTERNS.values():
        found.extend(m.group(0) for m in pattern.finditer(text))
    # de-dup, preserve first-seen order
    seen: set[str] = set()
    ordered: list[str] = []
    for lit in found:
        if lit not in seen:
            seen.add(lit)
            ordered.append(lit)
    return ordered


class InstructionProcessor(HEXTProcessor):
    processor_type = "semantic.instruction"
    version = "1.0.0"
    consumes = ["observation"]
    produces = ["diagram"]

    def process(self, event: HextObject) -> list[HextObject]:
        instruction_text = event.payload.get("instruction_text", "")
        literals_given = extract_literals(instruction_text)

        payload = {
            "stage": "instruction",
            "instruction_id": event.payload.get("instruction_id", event.id),
            "trajectory_id": event.payload.get("trajectory_id", event.id),
            "instruction_text": instruction_text,
            "literals_given": literals_given,
            "required_graph": event.payload.get("required_graph", {}),
            "generated_graph": event.payload.get("generated_graph", {}),
            "generated_text": event.payload.get("generated_text", ""),
            "candidate_labels": event.payload.get("candidate_labels", {}),
            "group": event.payload.get("group"),
        }
        return [
            derive_event(
                source=f"processor:{self.processor_type}",
                event_type="diagram",
                parent=event,
                payload=payload,
                metadata={"stage": "instruction"},
            )
        ]
