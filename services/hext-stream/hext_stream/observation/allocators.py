"""RFC-HEXT013 §4-6: UUID, timestamp, sequence, and digest allocation.

Existing runtime deviation this module corrects going forward (see
RFC-HEXT013 editorial note): ``schema/base.py``'s ``HextObject.id`` default
factory mints UUIDv4 (``f"hext:{uuid4()}"``), not the UUIDv7 RFC-HEXT001
§3.1 recommends and RFC-HEXT013 §4 requires at this layer. This module does
not change that default (changing it would touch a shared, working schema
default used by many callers outside the Observation Runtime's boundary,
including CTS fixtures that construct HextObjects directly with their own
IDs); it instead gives the Observation Driver its own, spec-conformant
allocation path for objects that pass through it.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


def allocate_uuid7() -> str:
    """RFC-HEXT013 §4 Rule 1: mint a UUIDv7-based HextObject id."""
    return f"hext:{uuid.uuid7()}"


def is_valid_uuid7(candidate: str) -> bool:
    """RFC-HEXT013 §4 Rule 2: verify a caller-supplied id is a real UUIDv7."""
    prefix = "hext:"
    raw = candidate[len(prefix):] if candidate.startswith(prefix) else candidate
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return False
    return parsed.version == 7


class TimestampAllocator:
    """RFC-HEXT013 §5.1: per-stream monotonic wall-clock timestamp allocation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[str, datetime] = {}

    def allocate(self, stream: str) -> datetime:
        now = datetime.now(timezone.utc)
        with self._lock:
            prior = self._last.get(stream)
            if prior is not None and now <= prior:
                now = prior + timedelta(microseconds=1)
            self._last[stream] = now
            return now


class SequenceAllocator:
    """RFC-HEXT013 §5.2: per-stream monotonic sequence counter.

    No sequence-allocation mechanism existed anywhere in the reference
    runtime prior to this module (verified during RFC-HEXT013 drafting);
    this is new, additive machinery, not a formalization of prior behavior.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}

    def allocate(self, stream: str) -> int:
        with self._lock:
            next_value = self._counters.get(stream, 0)
            self._counters[stream] = next_value + 1
            return next_value

    def peek(self, stream: str) -> int:
        with self._lock:
            return self._counters.get(stream, 0)


def canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def compute_payload_digest(payload: dict[str, Any]) -> str:
    """RFC-HEXT013 §6 Rule 1: SHA-256(canonical_serialization(payload))."""
    digest = hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()
    return f"sha256:{digest}"
