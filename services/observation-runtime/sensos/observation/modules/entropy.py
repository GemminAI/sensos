"""Entropy (H) observation module."""

from __future__ import annotations

import math
import re
from typing import Any, Dict

from sensos.abi.nvs74.module import ObservationModule


class EntropyModule(ObservationModule):
    """
    Measures information source entropy H of the generated stream.
    """

    def measure(self, text: str, context: Dict[str, Any]) -> float:
        words = re.findall(r"\w+", text.lower())
        if not words:
            return 0.9
        word_counts: Dict[str, int] = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1
        entropy = 0.0
        total_words = len(words)
        for count in word_counts.values():
            p = count / total_words
            entropy -= p * math.log2(p)
        return min(max(entropy / 8.0, 0.1), 0.95)
