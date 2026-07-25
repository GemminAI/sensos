"""RFC-HEXT014 §3: factory functions for the six telemetry event types.

Only ``processor.started``/``processor.completed``/``processor.failed`` and
``runtime.state`` are constructed here — these are the types nothing in the
reference runtime emits today. ``semantic.metric`` and ``controller.command``
are NOT constructed by this module: they already exist, produced by the
EXP-4010 processor chain and the base Processor Pipeline's Controller stage
respectively (see RFC-HEXT014 §3.4-3.5's amendment notes); Telemetry Runtime
consumes those, it does not mint them.
"""

from __future__ import annotations

from hext_stream.schema.base import HextObject, utcnow


def processor_started(
    *,
    source: str,
    processor_id: str,
    processor_type: str,
    input_object_id: str,
    parent_id: str | None = None,
) -> HextObject:
    """RFC-HEXT014 §3.1."""
    return HextObject(
        timestamp=utcnow(),
        source=source,
        type="processor.started",
        payload={
            "processor_id": processor_id,
            "processor_type": processor_type,
            "input_object_id": input_object_id,
            "parent_id": parent_id,
        },
    )


def processor_completed(
    *,
    source: str,
    processor_id: str,
    processor_type: str,
    input_object_id: str,
    output_object_id: str,
    execution_time_ms: float,
) -> HextObject:
    """RFC-HEXT014 §3.2."""
    return HextObject(
        timestamp=utcnow(),
        source=source,
        type="processor.completed",
        payload={
            "processor_id": processor_id,
            "processor_type": processor_type,
            "input_object_id": input_object_id,
            "output_object_id": output_object_id,
            "execution_time_ms": execution_time_ms,
        },
    )


def processor_failed(
    *,
    source: str,
    processor_id: str,
    processor_type: str,
    input_object_id: str,
    error_code: str,
    error_message: str,
) -> HextObject:
    """RFC-HEXT014 §3.3."""
    return HextObject(
        timestamp=utcnow(),
        source=source,
        type="processor.failed",
        payload={
            "processor_id": processor_id,
            "processor_type": processor_type,
            "input_object_id": input_object_id,
            "error_code": error_code,
            "error_message": error_message,
        },
    )


def runtime_state(*, source: str, state: str, previous_state: str | None) -> HextObject:
    """RFC-HEXT014 §3.6."""
    return HextObject(
        timestamp=utcnow(),
        source=source,
        type="runtime.state",
        payload={"state": state, "previous_state": previous_state},
    )
