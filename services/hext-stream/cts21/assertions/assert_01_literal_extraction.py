"""ASSERT-01: Literal Extraction Conformance (CTS-21.1).

CTS-21.md §4.1: assert extracted L == L_testcase (zero false positives), via
mechanical regex/syntax rules only.
"""

from __future__ import annotations

from typing import Any


def extract(tc: dict[str, Any]) -> set[str]:
    """Real extractor: hext_stream.processors.semantic.instruction_processor.extract_literals."""
    from hext_stream.processors.semantic.instruction_processor import extract_literals

    return set(extract_literals(tc["user_instruction"]))


def verify(extracted_L: set[str], expected_L: set[str], case_id: str) -> tuple[bool, str]:
    """Ported verbatim from CTS-21.md §5 verify_assert_01_literal_extraction."""
    if extracted_L != expected_L:
        return False, (
            f"[FAIL] ASSERT-01: Literal extraction mismatch in {case_id}. "
            f"Expected {expected_L}, got {extracted_L}"
        )
    return True, "[PASS] ASSERT-01: Literal extraction verified."
