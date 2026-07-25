"""Extended HEXT object type registry — v1.1 Processor Extension."""

from __future__ import annotations

from hext_stream.schema.base import HextObjectType

# Core v1.0 types (unchanged ABI)
CORE_TYPES: frozenset[str] = frozenset(
    t.value for t in (
        HextObjectType.OBSERVATION,
        HextObjectType.TRAJECTORY,
        HextObjectType.TRAJECTORY_FLOW,
        HextObjectType.REPLAY,
        HextObjectType.CONTROLLER,
        HextObjectType.REALITY,
        HextObjectType.DIAGNOSTIC,
        HextObjectType.METRICS,
    )
)

# v1.1 extension types — remain ordinary HextObjects
PROCESSOR_EXTENSION_TYPES: frozenset[str] = frozenset(
    t.value for t in (
        HextObjectType.HOM,
        HextObjectType.DIAGRAM,
        HextObjectType.REWRITE,
        HextObjectType.KAN_COMPLETION,
        HextObjectType.CONTROLLER_COMMAND,
        HextObjectType.SURFACE,
        # EXP-4010 Semantic Observation Processor Extension
        HextObjectType.EXPANSION_CANDIDATE,
        HextObjectType.SEMANTIC_METRIC,
    )
)

# RC1 Theory Runtime / DevTools Human Annotation — domain objects, not
# telemetry-about-the-runtime (RFC-HEXT014 §1's RC1 clarification)
THEORY_AND_ANNOTATION_TYPES: frozenset[str] = frozenset(
    t.value for t in (
        HextObjectType.THEORY_CONFIG,
        HextObjectType.HUMAN_FEEDBACK,
    )
)

ALL_REGISTERED_TYPES: frozenset[str] = (
    CORE_TYPES | PROCESSOR_EXTENSION_TYPES | THEORY_AND_ANNOTATION_TYPES
)


def is_registered_type(event_type: str) -> bool:
    return event_type in ALL_REGISTERED_TYPES


def is_processor_extension_type(event_type: str) -> bool:
    return event_type in PROCESSOR_EXTENSION_TYPES
