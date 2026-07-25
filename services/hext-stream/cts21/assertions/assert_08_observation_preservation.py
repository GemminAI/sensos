"""ASSERT-08: Observation Preservation Conformance (CTS-21.8)."""

from __future__ import annotations

from hext_stream.schema.base import HextObject


def extract(runtime, topic: str) -> str | None:
    from hext_stream.schema.replay import ReplayMode, ReplayRequest

    events = runtime.replay(ReplayRequest(topic=topic, mode=ReplayMode.LAST_N, last_n=500))
    seeds = [e for e in events if e.type == "observation"]
    if not seeds:
        return None
    return seeds[0].payload.get("instruction_text")


def verify(current_instruction: str | None, instruction_original: str, case_id: str) -> tuple[bool, str]:
    """Ported verbatim from CTS-21.md §5 verify_assert_08_observation_preservation."""
    if current_instruction != instruction_original:
        return False, (
            f"[FAIL] ASSERT-08: Observation mutated in {case_id}! "
            f"Original: '{instruction_original}', Mutated: '{current_instruction}'"
        )
    return True, "[PASS] ASSERT-08: Observation preservation (Original Instruction Immutability) verified."
