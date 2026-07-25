"""Memory similarity observation module."""

from __future__ import annotations

import math
import re
from typing import Any, Dict

from sensos.abi.nvs74.module import ObservationModule


class MemorySimilarityModule(ObservationModule):
    """
    Measures geometric similarity (sim) to crystallized safe trajectories.
    """

    def measure(self, text: str, context: Dict[str, Any]) -> float:
        safe_memories = context.get("safe_memories", [])
        words = re.findall(r"\w+", text.lower())
        if not words or not safe_memories:
            return 0.1

        max_similarity = 0.0
        for benchmark in safe_memories:
            benchmark_words = re.findall(r"\w+", benchmark.lower())
            common_words = set(words).intersection(set(benchmark_words))
            if words and benchmark_words:
                sim = len(common_words) / math.sqrt(len(words) * len(benchmark_words))
                max_similarity = max(max_similarity, sim)
        return max(max_similarity, 0.05)
