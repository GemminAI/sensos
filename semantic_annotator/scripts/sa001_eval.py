#!/usr/bin/env python3
"""SA001 evaluation harness.

Feeds a small, fixed sample set of Observations (sa001_samples.ndjson)
through the LLM-backed Annotator, running against a real vLLM server via
RuntimeBridge, and reports the metrics defined in
docs/handoff/HANDOFF_SA001_RUNPOD_BASELINE.md §7: JSON Validity, Schema
Conformance, Determinism, Latency, Token Efficiency.

This script is SA001-specific instrumentation, not part of the
semantic-annotator package itself: it deliberately does not touch
cli.py's hardcoded-Annotator gap (ARCHITECTURE_REVIEW.md §4 item 3),
which is separate, later work (see ARCHITECTURE_REVIEW.md's roadmap).

Everything printed under "Observed" is a real measurement from this run,
never an invented number (handoff §11 principle 7) -- if a run reports
NaN for a metric, that means zero applicable calls, not a fabricated 0.

Usage (inside the semantic-annotator container, against a running vLLM):
    RUNTIME_BRIDGE_URL=http://vllm:8000 GEMMA_MODEL_ID=<model> \\
        python scripts/sa001_eval.py --samples scripts/sa001_samples.ndjson
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic_annotator.llm_annotator import (
    LLMAnnotator,
    LLMResponseNotJSONError,
    LLMSchemaViolationError,
)
from semantic_annotator.models import Observation
from semantic_annotator.runtime_bridge import (
    CompletionResult,
    RuntimeBridgeError,
    VLLMRuntimeBridge,
)


@dataclass(frozen=True, slots=True)
class _CallRecord:
    latency_s: float
    prompt_tokens: int
    completion_tokens: int


class _InstrumentedBridge:
    """Wraps a RuntimeBridge to record latency/token usage per call.

    Exists only so this eval script can measure Latency/Token Efficiency
    (§7) using the exact same call LLMAnnotator makes, instead of issuing
    a second, separate HTTP request that would double the cost and risk
    measuring a different (non-deterministic) response than the one
    actually validated for JSON/schema conformance.
    """

    def __init__(self, inner: VLLMRuntimeBridge) -> None:
        self._inner = inner
        self.calls: list[_CallRecord] = []

    def complete(self, *, system_prompt: str, user_prompt: str) -> CompletionResult:
        t0 = time.monotonic()
        result = self._inner.complete(system_prompt=system_prompt, user_prompt=user_prompt)
        self.calls.append(
            _CallRecord(
                latency_s=time.monotonic() - t0,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )
        )
        return result


def _load_samples(path: Path) -> list[Observation]:
    observations = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        observations.append(
            Observation(
                id=raw["id"],
                source=raw["source"],
                timestamp=datetime.fromisoformat(raw["timestamp"]),
                payload=raw.get("payload", {}),
            )
        )
    return observations


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return float("nan")
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * p))
    return sorted_values[idx]


def _pct(numerator: int, denominator: int) -> float:
    return 100.0 * numerator / denominator if denominator else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser(description="SA001 evaluation harness")
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument(
        "--runs", type=int, default=5, help="repeats per Observation, for Determinism (§7)"
    )
    args = parser.parse_args()

    base_url = os.environ["RUNTIME_BRIDGE_URL"]
    model = os.environ["GEMMA_MODEL_ID"]
    bridge = _InstrumentedBridge(VLLMRuntimeBridge(base_url=base_url, model=model))
    annotator = LLMAnnotator(bridge)

    samples = _load_samples(args.samples)

    total_calls = 0
    json_valid = 0
    schema_conformant = 0
    determinism_matches = 0
    determinism_pairs = 0

    for observation in samples:
        label_sets: list[frozenset[tuple[str, float, str | None]]] = []
        for _ in range(args.runs):
            total_calls += 1
            try:
                annotated = annotator.annotate(observation)
            except LLMResponseNotJSONError as exc:
                print(f"[{observation.id}] JSON validity failure: {exc}", file=sys.stderr)
                continue
            except LLMSchemaViolationError as exc:
                json_valid += 1
                print(f"[{observation.id}] schema conformance failure: {exc}", file=sys.stderr)
                continue
            except RuntimeBridgeError as exc:
                print(f"[{observation.id}] transport failure: {exc}", file=sys.stderr)
                continue

            json_valid += 1
            schema_conformant += 1
            label_sets.append(
                frozenset(
                    (a.label, round(a.confidence, 6), a.taxonomy) for a in annotated.annotations
                )
            )

        for i in range(1, len(label_sets)):
            determinism_pairs += 1
            if label_sets[i] == label_sets[0]:
                determinism_matches += 1

    latencies = sorted(c.latency_s for c in bridge.calls)
    token_counts = [c.prompt_tokens + c.completion_tokens for c in bridge.calls]

    print("=== SA001 Evaluation — Observed (not Target) ===")
    print(
        f"Observations: {len(samples)}, runs/observation: {args.runs}, "
        f"total calls: {total_calls}"
    )
    print(f"JSON Validity:      {_pct(json_valid, total_calls):.1f}%  (target: 100%)")
    print(f"Schema Conformance: {_pct(schema_conformant, total_calls):.1f}%  (target: 100%)")
    if determinism_pairs:
        print(
            f"Determinism:        {_pct(determinism_matches, determinism_pairs):.1f}%  "
            f"({determinism_pairs} pairs; target: TBD, set from this baseline)"
        )
    else:
        print("Determinism:        no repeat pairs available (target: TBD, set from this baseline)")
    if latencies:
        p50 = _percentile(latencies, 0.50)
        p95 = _percentile(latencies, 0.95)
        print(f"Latency p50/p95 (s): {p50:.3f} / {p95:.3f}  (target: TBD, set from this baseline)")
    if token_counts:
        avg_tokens = sum(token_counts) / len(token_counts)
        print(
            f"Token efficiency:   {avg_tokens:.1f} tokens/call avg "
            "(target: TBD, set from this baseline)"
        )


if __name__ == "__main__":
    main()
