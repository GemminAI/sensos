"""Token-only facts about a finished generation (no hidden state is read).

Two facts are kept apart on purpose and never folded into one flag:

* ``reached_max_length``: the generation stopped because it hit ``max_tokens`` without an EOS.
* the repetition condition: in the last ``tail`` generated tokens, the share of *distinct* token
  n-grams among all n-grams is at most ``max_distinct_ratio`` (``n``-grams of length ``n``).

Both are functions of the token ids alone, so they stay independent of the hidden states that are
later measured.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

TAIL = 1024
NGRAM = 16
MAX_DISTINCT_RATIO = 0.2


def repetition_condition(
    token_ids: Sequence[int],
    *,
    tail: int = TAIL,
    n: int = NGRAM,
    max_distinct_ratio: float = MAX_DISTINCT_RATIO,
) -> dict[str, Any]:
    """The repetition condition on the last ``tail`` tokens. ``evaluated`` is False (and ``met`` is
    False) when fewer than ``tail`` tokens exist, so a short generation is never called repetitive."""
    ids = [int(i) for i in token_ids]
    out: dict[str, Any] = {
        "tail": tail,
        "ngram": n,
        "max_distinct_ratio": max_distinct_ratio,
        "evaluated": False,
        "distinct_ratio": None,
        "met": False,
    }
    if len(ids) < tail or tail < n:
        return out
    window = ids[-tail:]
    grams = [tuple(window[i : i + n]) for i in range(tail - n + 1)]
    ratio = len(set(grams)) / len(grams)
    out.update(evaluated=True, distinct_ratio=ratio, met=ratio <= max_distinct_ratio)
    return out


def outcome(token_ids: Sequence[int], finish_reason: str | None) -> dict[str, Any]:
    """Both facts, side by side."""
    return {
        "reached_max_length": finish_reason == "length",
        "finish_reason": finish_reason,
        "repetition": repetition_condition(token_ids),
        "n_generated": len(token_ids),
    }
