"""ASSERT-02: Controller Command Generation Conformance (CTS-21.2).

CTS-21.md §4.2: once LCF < 1.0 (floor), a `type: "controller.command"` HextObject with
`command: "hard_lock"`, `gain_multiplier: 0.0` must be deterministically generated.

Implementation note (not a spec divergence, just vocabulary): the real controller
processor (`hext_stream/processors/semantic/controller_processor.py`) emits
`payload.action` (ALLOW/WARN/SOFT_LIMIT/HARD_LOCK) and `payload.gain`, not literally
`command`/`gain_multiplier`. Mapped 1:1 below (`action=="hard_lock"` -> `command=
"hard_lock"`, `gain` -> `gain_multiplier`) since it's the same signal under a different
field name, not a behavioral difference.
"""

from __future__ import annotations

import math
from typing import Any

from hext_stream.schema.base import HextObject


def extract(published: list[HextObject], tc: dict[str, Any]) -> tuple[set[str], dict[str, Any]]:
    literals_given = set(tc["literal_constraints_given"])
    agent_output_text = tc.get("agent_output_text", "")
    preserved_L = {lit for lit in literals_given if lit in agent_output_text}

    commands = [e for e in published if e.type == "controller.command"]
    generated_command: dict[str, Any] = {}
    if commands:
        payload = commands[-1].payload
        generated_command = {"type": "controller.command"}
        if payload.get("action") == "hard_lock":
            generated_command["command"] = "hard_lock"
            generated_command["reason"] = "literal_constraint_violation"
            generated_command["gain_multiplier"] = payload.get("gain", 0.0)
        else:
            generated_command["command"] = payload.get("action")
            generated_command["gain_multiplier"] = payload.get("gain")

    return preserved_L, generated_command


def verify(
    literals_given: set[str],
    preserved_L: set[str],
    generated_command: dict[str, Any],
    case_id: str,
) -> tuple[bool, str]:
    """Ported verbatim from CTS-21.md §5 verify_assert_02_controller_command."""
    intersection = literals_given.intersection(preserved_L)
    lcf = len(intersection) / len(literals_given) if literals_given else 1.0
    lcf_floor = math.floor(lcf)

    if lcf_floor < 1.0:
        if generated_command.get("type") != "controller.command":
            return False, f"[FAIL] ASSERT-02: Wrong object type in {case_id}"
        if generated_command.get("command") != "hard_lock":
            return False, f"[FAIL] ASSERT-02: Command must be 'hard_lock' in {case_id}"
        if generated_command.get("gain_multiplier") != 0.0:
            return False, f"[FAIL] ASSERT-02: Gain multiplier must be 0.0 in {case_id}"
        return True, f"[PASS] ASSERT-02: Hard-Lock controller command generated correctly (LCF Floor: {lcf_floor})."
    return True, "[PASS] ASSERT-02: LCF is 1.0. Hard-Lock inactive."
