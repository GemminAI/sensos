"""Unit tests for harmony.py.

Fixture strings mirror the exact shape observed from a real
mlx-community/gpt-oss-20b-MXFP4-Q4 generation on this machine (see
mlx_runtime_bridge.py's module docstring), not invented syntax.
"""

from __future__ import annotations

import pytest

from semantic_annotator.harmony import HarmonyFormatError, extract_final_channel, looks_like_harmony

ANALYSIS_ONLY = (
    '<|channel|>analysis<|message|>We need to produce JSON array of annotation '
    "objects. The input: \"The stock market crashed today.\"\n\nWe need to "
    "identify relevant labels."
)

ANALYSIS_THEN_FINAL = (
    "<|channel|>analysis<|message|>We need to produce a JSON array. Let's "
    'produce two.\n\nYes.<|end|><|start|>assistant<|channel|>final<|message|>'
    '[{"label":"StockMarketCrash","confidence":0.9,"taxonomy":"FinancialEvent"},'
    '{"label":"InvestorPanic","confidence":0.8,"taxonomy":"InvestorEmotion"}]'
)

ANALYSIS_THEN_FINAL_WITH_TRAILING_RETURN = ANALYSIS_THEN_FINAL + "<|return|>"

PLAIN_TEXT = "hello, this is a completely ordinary completion with no Harmony markers."


# -- looks_like_harmony --------------------------------------------------


def test_looks_like_harmony_false_for_plain_text() -> None:
    assert looks_like_harmony(PLAIN_TEXT) is False


def test_looks_like_harmony_true_when_channel_marker_present() -> None:
    assert looks_like_harmony(ANALYSIS_ONLY) is True


# -- extract_final_channel: happy path ------------------------------------


def test_extract_final_channel_returns_final_message() -> None:
    content = extract_final_channel(ANALYSIS_THEN_FINAL)
    assert content == (
        '[{"label":"StockMarketCrash","confidence":0.9,"taxonomy":"FinancialEvent"},'
        '{"label":"InvestorPanic","confidence":0.8,"taxonomy":"InvestorEmotion"}]'
    )


def test_extract_final_channel_strips_trailing_return_marker() -> None:
    content = extract_final_channel(ANALYSIS_THEN_FINAL_WITH_TRAILING_RETURN)
    assert content.endswith("]")
    assert "<|return|>" not in content


def test_extract_final_channel_result_is_valid_annotation_json() -> None:
    import json

    content = extract_final_channel(ANALYSIS_THEN_FINAL)
    parsed = json.loads(content)
    assert parsed == [
        {"label": "StockMarketCrash", "confidence": 0.9, "taxonomy": "FinancialEvent"},
        {"label": "InvestorPanic", "confidence": 0.8, "taxonomy": "InvestorEmotion"},
    ]


# -- extract_final_channel: analysis-only (no final channel reached) ------


def test_extract_final_channel_raises_when_only_analysis_channel_present() -> None:
    with pytest.raises(HarmonyFormatError, match="no 'final' channel"):
        extract_final_channel(ANALYSIS_ONLY)


def test_extract_final_channel_error_lists_channels_seen() -> None:
    with pytest.raises(HarmonyFormatError, match="analysis"):
        extract_final_channel(ANALYSIS_ONLY)


# -- extract_final_channel: malformed Harmony output -----------------------


def test_extract_final_channel_raises_on_unparseable_channel_marker() -> None:
    malformed = "<|channel|>"  # marker present but no channel name / <|message|>
    with pytest.raises(HarmonyFormatError, match="no parseable Harmony channel"):
        extract_final_channel(malformed)


def test_extract_final_channel_raises_on_empty_string() -> None:
    with pytest.raises(HarmonyFormatError):
        extract_final_channel("")


# -- extract_final_channel: multiple final segments (last one wins) -------


def test_extract_final_channel_uses_last_final_segment_if_more_than_one() -> None:
    text = (
        "<|channel|>analysis<|message|>thinking<|end|>"
        "<|start|>assistant<|channel|>final<|message|>first<|end|>"
        "<|start|>assistant<|channel|>final<|message|>second"
    )
    assert extract_final_channel(text) == "second"
