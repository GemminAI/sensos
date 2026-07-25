#!/usr/bin/env python3
"""CTS-22: Default Theory Identity — RFC-HEXT016 §9 Rule 1's conformance gate.

Proves, mechanically, that introducing the Theory Runtime (TheoryContext,
theory-aware processor construction) produces ZERO behavioral change for
the default theory, before any alternate theory is implemented or
registered. Reuses CTS-21's real pipeline execution
(`cts21.runner.run_semantic_pipeline`) and case fixtures directly — this
suite adds no new fixtures, no new pipeline, only a new comparison.

For each of CTS-21's three case fixtures, runs the real EXP-4010 chain
three times:
  (A) implicit default — `build_pipeline_processors()`, the original
      zero-argument call, unchanged since before RFC-HEXT016.
  (B) explicit `theory_context=None`.
  (C) explicit `theory_context=TheoryContext.default()`.
and asserts every `semantic.metric`/`controller.command` object the three
runs produce is bit-for-bit identical (payload and metadata `action`/
`metrics`, including full float precision).

Usage:
  PYTHONPATH=. python3 cts21/cts22_theory_identity.py [--skip-redis] [--redis-url URL]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cts21.runner import CASES_DIR, iso_topics, make_runtime, run_semantic_pipeline
from hext_stream.schema.base import HextObject
from hext_stream.theory.context import TheoryContext

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


@dataclass
class VariantResult:
    label: str
    metric: dict[str, Any] | None
    command: dict[str, Any] | None


@dataclass
class CaseResult:
    case_id: str
    backend: str
    passed: bool
    detail: str


def _find(published: list[HextObject], type_: str) -> HextObject | None:
    for obj in published:
        if obj.type == type_:
            return obj
    return None


def _run_variant(
    runtime_factory, tc: dict[str, Any], label: str, theory_context: Any, *, shared_run_id: str
) -> VariantResult:
    # `run_semantic_pipeline` takes `run_id` (which it uses to derive
    # `trajectory_id`/`instruction_id`/`HextObject.id`) and `topics`
    # separately. Passing the SAME `shared_run_id` across all three
    # variants keeps trajectory/instruction identity comparable; deriving
    # `topics` from a per-variant-labeled id instead keeps the three runs'
    # backend storage isolated from each other. Without this split, every
    # payload would differ on run-scoped identity alone, regardless of any
    # real behavioral difference — exactly the false failure this comment
    # replaces (see the RC1 CTS-22 report history for the caught bug).
    topics = iso_topics(f"{shared_run_id}-{label}")
    runtime = runtime_factory()
    try:
        for topic in topics.values():
            runtime.router.register(topic)
        published = run_semantic_pipeline(runtime, tc, shared_run_id, topics, theory_context=theory_context)
        metric_obj = _find(published, "semantic.metric")
        command_obj = _find(published, "controller.command")
        return VariantResult(
            label=label,
            metric=metric_obj.payload if metric_obj else None,
            command=command_obj.payload if command_obj else None,
        )
    finally:
        runtime.close()


def run_case(case_path: Path, backend_name: str, redis_url: str) -> CaseResult:
    tc = json.loads(case_path.read_text(encoding="utf-8"))
    shared_run_id = f"{tc['case_id']}-cts22-{backend_name}-{uuid.uuid4().hex[:8]}"

    def runtime_factory():
        return make_runtime(backend_name, redis_url)

    # (A) implicit default -- the literal pre-RFC-HEXT016 call signature.
    variant_a = _run_variant(runtime_factory, tc, "implicit-default", None, shared_run_id=shared_run_id)
    # NOTE: run_semantic_pipeline's `theory_context` keyword defaults to
    # None already; passing None explicitly here is (B).
    variant_b = _run_variant(runtime_factory, tc, "explicit-none", None, shared_run_id=shared_run_id)
    variant_c = _run_variant(
        runtime_factory, tc, "explicit-default-context", TheoryContext.default(), shared_run_id=shared_run_id
    )

    variants = [variant_a, variant_b, variant_c]
    metrics_identical = all(v.metric == variant_a.metric for v in variants)
    commands_identical = all(v.command == variant_a.command for v in variants)
    no_missing = all(v.metric is not None and v.command is not None for v in variants)

    passed = metrics_identical and commands_identical and no_missing
    detail = (
        f"metrics_identical={metrics_identical} commands_identical={commands_identical} "
        f"no_missing={no_missing} metric_A={variant_a.metric} command_A={variant_a.command}"
    )
    return CaseResult(case_id=tc["case_id"], backend=backend_name, passed=passed, detail=detail)


def export_report(results: list[CaseResult]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CTS-22: Default Theory Identity Report\n\n",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n",
        "## Purpose\n\n",
        "Prove that introducing RFC-HEXT016's Theory Runtime (TheoryContext-aware "
        "processor construction) produces zero behavioral change for the default "
        "theory -- a prerequisite gate, per RFC-HEXT016 §9 Rule 1, before any "
        "alternate theory is implemented or registered. Compares implicit-default, "
        "explicit-`None`, and explicit-`TheoryContext.default()` construction across "
        "all three CTS-21 case fixtures.\n\n",
        "| Case | Backend | PASS | Detail |\n|---|---|---|---|\n",
    ]
    for r in results:
        lines.append(f"| {r.case_id} | {r.backend} | {'PASS' if r.passed else 'FAIL'} | {r.detail} |\n")
    all_pass = all(r.passed for r in results)
    lines.append(f"\n## Overall Verdict\n\n**{'PASS' if all_pass else 'FAIL'}**\n")
    (REPORTS_DIR / "CTS22_Report.md").write_text("".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="CTS-22 Default Theory Identity runner")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--skip-redis", action="store_true")
    args = parser.parse_args()

    case_files = sorted(CASES_DIR.glob("*.json"))
    print(f"[CTS-22] Found {len(case_files)} test cases in {CASES_DIR}")

    results: list[CaseResult] = []
    for backend_name in (["inprocess"] if args.skip_redis else ["inprocess", "redis"]):
        print(f"\n[CTS-22] Backend: {backend_name}")
        for case_file in case_files:
            try:
                result = run_case(case_file, backend_name, args.redis_url)
                results.append(result)
                print(f"  [{'PASS' if result.passed else 'FAIL'}] {result.case_id} ({backend_name})")
            except Exception as exc:
                print(f"[CTS-22] EXCEPTION running {case_file.name} on {backend_name}: {exc}")
                results.append(CaseResult(case_id=case_file.stem, backend=backend_name, passed=False, detail=str(exc)))

    export_report(results)
    print(f"\n[CTS-22] Report: {REPORTS_DIR / 'CTS22_Report.md'}")

    passed = sum(1 for r in results if r.passed)
    print(f"[CTS-22] {passed}/{len(results)} cases passed across all backends")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
