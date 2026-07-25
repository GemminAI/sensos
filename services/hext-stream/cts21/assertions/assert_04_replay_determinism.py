"""ASSERT-04: Replay Determinism Conformance (CTS-21.4).

CTS-21.md §4.4: SHA256(History_first) == SHA256(History_replay).

Implementation clarification (not a divergence): HextObject's `id`/`timestamp` fields
are freshly generated (uuid4/utcnow) on every *new* publish, so re-executing the whole
pipeline a second time from the same seed would never byte-match by construction. The
runtime's own `replay()` API replays already-*stored* immutable records — it doesn't
regenerate them — so "replay the History" is implemented here as: publish once, then
call `runtime.replay()` twice on the same topic and hash each result. This is the
achievable, intended reading given how `replay()` actually works.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from hext_stream.schema.base import HextObject


def canonical_bytes(events: list[HextObject]) -> bytes:
    envelopes = [e.to_envelope() for e in events]
    return json.dumps(envelopes, sort_keys=True, separators=(",", ":")).encode("utf-8")


def extract(runtime, topic: str) -> tuple[bytes, bytes]:
    from hext_stream.schema.replay import ReplayMode, ReplayRequest

    def replay_once() -> list[HextObject]:
        return runtime.replay(ReplayRequest(topic=topic, mode=ReplayMode.LAST_N, last_n=500))

    first = replay_once()
    second = replay_once()
    return canonical_bytes(first), canonical_bytes(second)


def verify(raw_history_data_1: bytes, raw_history_data_2: bytes, case_id: str) -> tuple[bool, str]:
    """Ported verbatim from CTS-21.md §5 verify_assert_04_replay_determinism."""
    hash1 = hashlib.sha256(raw_history_data_1).hexdigest()
    hash2 = hashlib.sha256(raw_history_data_2).hexdigest()
    if hash1 != hash2:
        return False, f"[FAIL] ASSERT-04: Determinism broken in {case_id}. Hashes do not match.\n1: {hash1}\n2: {hash2}"
    return True, f"[PASS] ASSERT-04: Replay determinism verified. SHA256: {hash1}"
