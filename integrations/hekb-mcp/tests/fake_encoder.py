"""Deterministic, fast fake SemanticEncoder for unit tests.

NOT a semantic embedding — a character-trigram hashing vector. It shares
enough structure with a real encoder (fixed dimension, deterministic,
similarity correlates with shared substrings) to exercise
Projector/AttractorResolver/RetrievalRenderer/ObservationEngine plumbing
without paying the real model's load cost in every test run. It is not
used to validate any RFC-NVS-0100 metric — that validation runs once,
separately, against the real SentenceTransformerEncoder (see
run_rfc0100_verification.py / EXPERIMENT_REPORT_RFC0100.md).
"""

from __future__ import annotations

import hashlib

import numpy as np


class FakeTrigramEncoder:
    dimension = 32

    def encode(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dimension, dtype=np.float64)
        padded = f"  {text}  "
        for i in range(len(padded) - 2):
            trigram = padded[i : i + 3]
            h = int(hashlib.sha256(trigram.encode("utf-8")).hexdigest(), 16)
            vec[h % self.dimension] += 1.0
        if np.linalg.norm(vec) < 1e-12:
            vec[0] = 1.0
        return vec
