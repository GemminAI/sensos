"""ASSERT-06: Pipeline Topology Conformance (CTS-21.6).

CTS-21 Specification v1.0 Candidate §4.6: the EXP-4010 processor pipeline packets must
transition in exactly [EXP-4010] §4's order, with monotonic-non-decreasing timestamps
and strictly continuous sequence numbers.

MIGRATION NOTE: this supersedes the previous version of this module, which (per
Specification_Divergence_Report.md's DIVERGENCE-02) tested the *original v1.1*
reference pipeline (RFC-HEXT004 §7: trajectory/flow/hom/diagram/rewrite/controller)
because that was the only pipeline whose stage names satisfied the *old* CTS-21 draft's
`expected_flow`. CTS-21 v1.0 Candidate's `expected_flow` now names the EXP-4010 semantic
pipeline's own stages directly, so this module now exercises
`build_pipeline_processors()` (the real semantic pipeline) instead of the v1.1 one —
divergence resolved, not worked around.
"""

from __future__ import annotations

from typing import Any

from hext_stream.schema.base import HextObject

EXPECTED_FLOW = [
    "instruction",
    "required_category",
    "generated_category",
    "expansion_detector",
    "lcf_detector",
    "sed_calculator",
    "oi_calculator",
    "if_calculator",
    "gain_scheduler",
    "controller",
]

# processor_type (stamped by stamp_processor_metadata) -> EXPECTED_FLOW stage name.
_PROCESSOR_TYPE_TO_STAGE_NAME = {
    "semantic.instruction": "instruction",
    "semantic.required_category": "required_category",
    "semantic.generated_category": "generated_category",
    "semantic.expansion_detector": "expansion_detector",
    "semantic.lcf_detector": "lcf_detector",
    "semantic.sed_calculator": "sed_calculator",
    "semantic.oi_calculator": "oi_calculator",
    "semantic.if_calculator": "if_calculator",
    "semantic.gain_scheduler": "gain_scheduler",
    "semantic.controller": "controller",
}


def extract(published: list[HextObject]) -> list[dict[str, Any]]:
    """One log entry per EXPECTED_FLOW stage, first time its processor appears in
    publish order (each stage runs exactly once per trajectory in this pipeline, except
    expansion_detector, which may emit multiple expansion.candidate objects before its
    single expansion_summary diagram — only the first entry per stage is kept)."""
    logs: list[dict[str, Any]] = []
    seen_stages: set[str] = set()
    seq = 0
    for e in published:
        proc_type = e.metadata.get("processor", {}).get("type")
        stage_name = _PROCESSOR_TYPE_TO_STAGE_NAME.get(proc_type)
        if stage_name is None or stage_name in seen_stages:
            continue
        seen_stages.add(stage_name)
        logs.append({"name": stage_name, "timestamp": e.timestamp.timestamp(), "sequence": seq})
        seq += 1
    return logs


def verify(ordered_processor_logs: list[dict[str, Any]], case_id: str) -> tuple[bool, str]:
    """Ported verbatim from CTS-21 v1.0 Candidate §5 verify_assert_06_pipeline_topology."""
    filtered_logs = [log for log in ordered_processor_logs if log["name"] in EXPECTED_FLOW]

    names = [log["name"] for log in filtered_logs]
    if names != EXPECTED_FLOW:
        return False, f"[FAIL] ASSERT-06: Pipeline sequence violation in {case_id}. Got {names}"

    for i in range(len(filtered_logs) - 1):
        curr_log = filtered_logs[i]
        next_log = filtered_logs[i + 1]
        if curr_log["timestamp"] > next_log["timestamp"]:
            return False, (
                f"[FAIL] ASSERT-06: Temporal anomaly detected in {case_id}. "
                f"{curr_log['name']} ({curr_log['timestamp']}) -> {next_log['name']} ({next_log['timestamp']})"
            )
        if curr_log["sequence"] + 1 != next_log["sequence"]:
            return False, (
                f"[FAIL] ASSERT-06: Sequence discontinuity in {case_id}. "
                f"{curr_log['name']} (Seq {curr_log['sequence']}) -> {next_log['name']} (Seq {next_log['sequence']})"
            )

    return True, "[PASS] ASSERT-06: Processor pipeline topology (Order & Continuity) verified."
