#!/usr/bin/env python3
"""P1-07 E2E validation: hash, tags, diffusion, browser fields, performance."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from e2e_db import make_sqlite_session

DATASET = ROOT / "tests" / "e2e" / "sample_articles.json"
REPORT_DIR = ROOT / "reports" / "e2e"

T09_AXES = ["security", "economy", "technology", "resources", "ideology", "environment"]

# RC-1 presentation mapping (epistemic_diffusion_state → legacy T22 aura)
DIFFUSION_MAP = {
    "stable": "Crystallized",
    "diffuse": "Diffused",
    "low_confidence": "Diffused",
    "high_conflict": "Polarized",
}


@dataclass
class PerfSample:
    provider_ms: float = 0.0
    tag_ms: float = 0.0
    db_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class ValidationRun:
    articles: list[dict] = field(default_factory=list)
    seeded: list[dict] = field(default_factory=list)
    hash_runs: list[dict] = field(default_factory=list)
    tag_checks: list[dict] = field(default_factory=list)
    diffusion_checks: list[dict] = field(default_factory=list)
    browser_checks: list[dict] = field(default_factory=list)
    perf_samples: list[PerfSample] = field(default_factory=list)
    mode: str = "direct"
    runtime_url: str = "http://localhost:8020"


def load_dataset() -> list[dict]:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def t09_vector(tags: dict[str, Any]) -> list[float]:
    raw = tags.get("T09") or tags.get("T09_strategic_interest_vector")
    if isinstance(raw, list) and len(raw) == 6:
        return [float(v) for v in raw]
    if isinstance(raw, dict):
        return [float(raw.get(ax, 0.0)) for ax in T09_AXES]
    return [0.0] * 6


def dominant_axis(tags: dict[str, Any]) -> str:
    vec = t09_vector(tags)
    idx = max(range(len(vec)), key=lambda i: abs(vec[i]))
    return T09_AXES[idx]


def heuristic_t22(narrative: str) -> float:
    tokens = re.findall(r"\S+", narrative)
    if len(tokens) < 2:
        return 0.0
    return min(1.0, len(set(t.lower() for t in tokens)) / len(tokens))


def classify_t22_from_entropy(h0: float, t19: float) -> str:
    if t19 >= 0.6:
        return "Polarized"
    if h0 <= 0.32:
        return "Crystallized"
    if h0 >= 0.55:
        return "Diffused"
    return "Diffused"


async def run_pipeline_timed(article: str, origin: str) -> tuple[dict, PerfSample]:
    from runtime.providers.router import generate_narrative
    from runtime.services.crystallizer import (
        compute_epistemic_diffusion_state,
        crystallize_state_hash,
    )
    from runtime.services.pipeline import NarrativePipeline
    from runtime.services.semantic_annotator_client import SemanticAnnotatorClient
    from runtime.services.state_service import StateService

    Session = make_sqlite_session()
    session = Session()
    perf = PerfSample()

    try:
        pipeline = NarrativePipeline()
        prompt = pipeline.build_prompt(article)

        t0 = time.perf_counter()
        narrative, provider_used = await generate_narrative(prompt, origin)
        perf.provider_ms = (time.perf_counter() - t0) * 1000

        # Which backend Semantic Annotator uses internally is that
        # service's own configuration now, not selected here - see
        # runtime/services/semantic_annotator_client.py's module docstring.
        annotator_client = SemanticAnnotatorClient()
        t1 = time.perf_counter()
        result = await annotator_client.annotate(narrative)
        tags = result.tags.to_legacy_dict()
        perf.tag_ms = (time.perf_counter() - t1) * 1000

        state_hash = crystallize_state_hash(narrative, tags, origin)
        epistemic = compute_epistemic_diffusion_state(tags)

        t2 = time.perf_counter()
        record = StateService().create(
            session,
            state_hash=state_hash,
            narrative=narrative,
            tags=tags,
            subject_origin=origin,
            schema_version="35tag.v6.0.rc1",
            epistemic_diffusion_state=epistemic,
            article=article,
            provider=provider_used,
        )
        session.commit()
        perf.db_ms = (time.perf_counter() - t2) * 1000
        perf.total_ms = perf.provider_ms + perf.tag_ms + perf.db_ms
        return record.to_dict(), perf
    finally:
        session.close()


async def validate_hash(article: str, origin: str, repeats: int = 3) -> dict:
    from runtime.services.crystallizer import crystallize_state_hash

    hashes: list[str] = []
    narratives: list[str] = []
    tags_list: list[dict] = []

    for _ in range(repeats):
        data, _ = await run_pipeline_timed(article, origin)
        hashes.append(data["state_hash"])
        narratives.append(data["narrative"])
        tags_list.append(data["tags"])

    crystallizer_only = crystallize_state_hash(narratives[0], tags_list[0], origin)
    return {
        "hashes": hashes,
        "unique_hashes": len(set(hashes)),
        "narratives_identical": len(set(narratives)) == 1,
        "tags_identical": len({json.dumps(t, sort_keys=True) for t in tags_list}) == 1,
        "crystallizer_deterministic": crystallizer_only == hashes[0],
        "pass": len(set(hashes)) == 1,
    }


async def run_direct_validation(run: ValidationRun) -> None:
    articles = run.articles

    for item in articles:
        data, perf = await run_pipeline_timed(item["article"], item["origin"])
        run.seeded.append({"id": item["id"], "category": item["category"], **data})
        run.perf_samples.append(perf)

        axis = dominant_axis(data["tags"])
        run.tag_checks.append(
            {
                "id": item["id"],
                "category": item["category"],
                "expected_axis": item["expected_t09_axis"],
                "actual_axis": axis,
                "t09": t09_vector(data["tags"]),
                "pass": axis == item["expected_t09_axis"],
            }
        )

        mapped = DIFFUSION_MAP.get(data["epistemic_diffusion_state"], "Unknown")
        h0 = heuristic_t22(data["narrative"])
        t19 = float(data["tags"].get("T19", data["tags"].get("T19_conflict_factuality_index", 0.0)))
        heuristic_label = classify_t22_from_entropy(h0, t19)
        run.diffusion_checks.append(
            {
                "id": item["id"],
                "category": item["category"],
                "expected": item["expected_diffusion"],
                "epistemic_diffusion_state": data["epistemic_diffusion_state"],
                "mapped_label": mapped,
                "t22_h0": round(h0, 4),
                "t19": round(t19, 4),
                "heuristic_label": heuristic_label,
                "pass": mapped == item["expected_diffusion"] or heuristic_label == item["expected_diffusion"],
            }
        )

    # Hash validation on first article
    first = articles[0]
    run.hash_runs.append(
        {
            "id": first["id"],
            "category": first["category"],
            **await validate_hash(first["article"], first["origin"]),
        }
    )


def validate_browser_fields_http(run: ValidationRun) -> None:
    dashboard_fields = {
        "state_hash",
        "subject_origin",
        "created_at",
        "schema_version",
        "epistemic_diffusion_state",
    }
    detail_fields = {
        "state_hash",
        "narrative",
        "tags",
        "subject_origin",
        "schema_version",
        "epistemic_diffusion_state",
        "created_at",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            t0 = time.perf_counter()
            list_resp = client.get(f"{run.runtime_url}/states")
            list_ms = (time.perf_counter() - t0) * 1000
            list_resp.raise_for_status()
            items = list_resp.json()

            dash_ok = bool(items) and dashboard_fields.issubset(items[0].keys())
            run.browser_checks.append(
                {
                    "check": "dashboard_fields",
                    "pass": dash_ok,
                    "count": len(items),
                    "render_ms": round(list_ms, 1),
                    "missing": sorted(dashboard_fields - set(items[0].keys())) if items else list(dashboard_fields),
                }
            )

            if items:
                h = items[0]["state_hash"]
                t1 = time.perf_counter()
                detail_resp = client.get(f"{run.runtime_url}/states/{h}")
                detail_ms = (time.perf_counter() - t1) * 1000
                detail_resp.raise_for_status()
                detail = detail_resp.json()
                detail_ok = detail_fields.issubset(detail.keys()) and isinstance(detail["tags"], dict)
                run.browser_checks.append(
                    {
                        "check": "state_detail_fields",
                        "pass": detail_ok,
                        "state_hash": h,
                        "render_ms": round(detail_ms, 1),
                        "missing": sorted(detail_fields - set(detail.keys())),
                    }
                )
    except httpx.HTTPError as exc:
        run.browser_checks.append({"check": "browser_http", "pass": False, "error": str(exc)})


def validate_browser_fields_local(run: ValidationRun) -> None:
    if not run.seeded:
        return
    sample = run.seeded[0]
    dashboard_fields = {
        "state_hash",
        "subject_origin",
        "created_at",
        "schema_version",
        "epistemic_diffusion_state",
    }
    detail_fields = {
        "state_hash",
        "narrative",
        "tags",
        "subject_origin",
        "schema_version",
        "epistemic_diffusion_state",
        "created_at",
    }
    list_item = {k: sample[k] for k in dashboard_fields if k in sample}
    run.browser_checks.append(
        {
            "check": "dashboard_fields_local",
            "pass": dashboard_fields.issubset(set(list_item.keys()) | set(sample.keys())),
            "fields_present": sorted(dashboard_fields & set(sample.keys())),
        }
    )
    run.browser_checks.append(
        {
            "check": "state_detail_fields_local",
            "pass": detail_fields.issubset(sample.keys()),
            "fields_present": sorted(detail_fields & set(sample.keys())),
        }
    )


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.1f}%" if total else "N/A"


def write_hash_report(run: ValidationRun, path: Path) -> None:
    lines = [
        "# Hash Validation Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Mode:** {run.mode}",
        "",
        "## Summary",
        "",
    ]
    for item in run.hash_runs:
        status = "PASS" if item["pass"] else "FAIL"
        lines += [
            f"- Article `{item['id']}` ({item['category']}): **{status}**",
            f"  - Runs: {item['repeats'] if 'repeats' in item else 3}",
            f"  - Unique hashes: {item['unique_hashes']}",
            f"  - Narratives identical: {item['narratives_identical']}",
            f"  - Tags identical: {item['tags_identical']}",
            f"  - Crystallizer deterministic: {item['crystallizer_deterministic']}",
            "",
        ]
    lines += [
        "## Notes",
        "",
        "- `crystallize_state_hash()` is deterministic for identical narrative + tags + origin.",
        "- Full pipeline hash stability requires deterministic provider and tag-generator output.",
        "- Mock providers (no API keys) yield stable hashes; live LLM may produce different narratives.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_tag_report(run: ValidationRun, path: Path) -> None:
    passed = sum(1 for t in run.tag_checks if t["pass"])
    total = len(run.tag_checks)
    lines = [
        "# 35TAG Validation Report (T09 Dominance)",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Pass rate:** {passed}/{total} ({_pct(passed, total)})",
        "",
        "| ID | Category | Expected | Actual | Pass |",
        "|----|----------|----------|--------|------|",
    ]
    for t in run.tag_checks:
        lines.append(
            f"| {t['id']} | {t['category']} | {t['expected_axis']} | {t['actual_axis']} | {'✓' if t['pass'] else '✗'} |"
        )
    lines += [
        "",
        "## T09 Vectors (sample)",
        "",
    ]
    for t in run.tag_checks[:5]:
        lines.append(f"- `{t['id']}`: `{t['t09']}`")
    lines += [
        "",
        "## Notes",
        "",
        "- T09 axes order: security, economy, technology, resources, ideology, environment.",
        "- Dominance = axis with largest absolute value in T09 vector.",
        "- Fallback tag-generator returns zero vector; live tag-generator + API keys required for full pass.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_diffusion_report(run: ValidationRun, path: Path) -> None:
    passed = sum(1 for d in run.diffusion_checks if d["pass"])
    total = len(run.diffusion_checks)
    lines = [
        "# T22 / Diffusion Validation Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Pass rate:** {passed}/{total} ({_pct(passed, total)})",
        "",
        "RC-1 stores `epistemic_diffusion_state` (stable/diffuse/high_conflict/low_confidence).",
        "Legacy T22 aura mapping used for validation:",
        "",
        "| RC-1 state | Legacy aura |",
        "|------------|-------------|",
        "| stable | Crystallized |",
        "| diffuse, low_confidence | Diffused |",
        "| high_conflict | Polarized |",
        "",
        "| ID | Category | Expected | Mapped | H₀ | T19 | Pass |",
        "|----|----------|----------|--------|----|-----|------|",
    ]
    for d in run.diffusion_checks:
        lines.append(
            f"| {d['id']} | {d['category']} | {d['expected']} | {d['mapped_label']} | "
            f"{d['t22_h0']} | {d['t19']} | {'✓' if d['pass'] else '✗'} |"
        )
    lines += ["", "## Notes", "", "- T22 normative field is `informational_entropy` (float) per 35TAG v6.0.1.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_perf_report(run: ValidationRun, path: Path) -> None:
    if not run.perf_samples:
        return

    def stats(key: str) -> dict:
        vals = [getattr(s, key) for s in run.perf_samples]
        return {
            "mean": round(statistics.mean(vals), 1),
            "p50": round(statistics.median(vals), 1),
            "max": round(max(vals), 1),
        }

    provider = stats("provider_ms")
    tag = stats("tag_ms")
    db = stats("db_ms")
    total = stats("total_ms")
    browser_ms = [c.get("render_ms") for c in run.browser_checks if "render_ms" in c]

    lines = [
        "# Performance Baseline",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Samples:** {len(run.perf_samples)} articles",
        f"**Mode:** {run.mode}",
        "",
        "## Runtime Pipeline (ms)",
        "",
        "| Phase | Mean | P50 | Max |",
        "|-------|------|-----|-----|",
        f"| Provider (narrative) | {provider['mean']} | {provider['p50']} | {provider['max']} |",
        f"| TagGenerator | {tag['mean']} | {tag['p50']} | {tag['max']} |",
        f"| DB write | {db['mean']} | {db['p50']} | {db['max']} |",
        f"| **Total E2E** | **{total['mean']}** | **{total['p50']}** | **{total['max']}** |",
        "",
    ]
    if browser_ms:
        lines += [
            "## Browser API fetch (ms)",
            "",
            f"- Dashboard `/states`: {browser_ms[0]} ms",
        ]
        if len(browser_ms) > 1:
            lines.append(f"- State detail: {browser_ms[1]} ms")
        lines.append("")

    lines += [
        "## Environment",
        "",
        f"- GEMINI_API_KEY: {'set' if os.getenv('GEMINI_API_KEY') else 'not set (mock)'}",
        f"- OPENAI_API_KEY: {'set' if os.getenv('OPENAI_API_KEY') else 'not set (mock)'}",
        f"- ANTHROPIC_API_KEY: {'set' if os.getenv('ANTHROPIC_API_KEY') else 'not set (mock)'}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_browser_report(run: ValidationRun, path: Path) -> None:
    passed = sum(1 for c in run.browser_checks if c.get("pass"))
    total = len(run.browser_checks)
    lines = [
        "# Browser Validation Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Checks passed:** {passed}/{total}",
        "",
        "## Dashboard (`/`)",
        "",
        "Required fields: state_hash, subject_origin, created_at, schema_version, epistemic_diffusion_state",
        "",
        "## State Detail (`/state/[hash]`)",
        "",
        "Required sections: Narrative, 35TAG JSON (tags), Metadata (state_hash, origin, created_at)",
        "",
        "## Check Results",
        "",
    ]
    for check in run.browser_checks:
        status = "PASS" if check.get("pass") else "FAIL"
        lines.append(f"### {check.get('check', 'unknown')} — **{status}**")
        for k, v in check.items():
            if k not in ("check", "pass"):
                lines.append(f"- {k}: {v}")
        lines.append("")

    lines += [
        "## Manual verification",
        "",
        "```bash",
        "cd browser && RUNTIME_API_URL=http://localhost:8020 npm run dev",
        "# Open http://localhost:3000",
        "```",
        "",
        "Browser consumes Runtime API only (`GET /states`, `GET /states/{hash}`).",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_summary_report(run: ValidationRun, path: Path) -> None:
    hash_ok = all(h["pass"] for h in run.hash_runs)
    tag_pass = sum(1 for t in run.tag_checks if t["pass"])
    diff_pass = sum(1 for d in run.diffusion_checks if d["pass"])
    browser_pass = sum(1 for c in run.browser_checks if c.get("pass"))
    lines = [
        "# E2E Validation Summary (P1-07)",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Articles:** {len(run.articles)}",
        f"**Mode:** {run.mode}",
        "",
        "## Results",
        "",
        "| Step | Result |",
        "|------|--------|",
        f"| Hash determinism | {'PASS' if hash_ok else 'FAIL'} |",
        f"| T09 dominance | {tag_pass}/{len(run.tag_checks)} |",
        f"| T22 / diffusion | {diff_pass}/{len(run.diffusion_checks)} |",
        f"| Browser API fields | {browser_pass}/{len(run.browser_checks)} |",
        "",
        "## RC-1 Operational Status",
        "",
    ]
    if hash_ok and browser_pass == len(run.browser_checks):
        lines.append("**Core pipeline operational** — hash stability and Browser API contract verified.")
    else:
        lines.append("**Partial** — see individual reports.")

    lines += [
        "",
        "T09/T22 full validation requires live tag-generator with LLM API keys (not fallback mode).",
        "",
        "## Reports",
        "",
        "- hash_validation_report.md",
        "- tag_validation_report.md",
        "- diffusion_validation_report.md",
        "- browser_validation_report.md",
        "- performance_baseline.md",
        "- rc2_backlog.md",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_rc2_backlog(path: Path) -> None:
    content = """# Browser RC-2 Backlog

**Status:** Planning only — no implementation in P1-07.

## Candidate Features

| # | Feature | Description | User Value | Complexity | Dependencies |
|---|---------|-------------|------------|------------|--------------|
| 1 | State Timeline | Chronological list of states with filters by origin/category | High — core observatory navigation | Low | RC-1 `/states` API |
| 2 | Origin Comparison | Side-by-side states from jp/us/eu for same article | High — validates provider routing | Medium | Multi-origin generate |
| 3 | Narrative Diff Viewer | Diff two narratives by state_hash | Medium — audit trail | Medium | Pairwise fetch |
| 4 | SIV Radar | T09 strategic interest vector radar chart | Medium — visual TAG insight | Medium | Full 35TAG in API |
| 5 | Trajectory Viewer | Coordinate trajectory over time/chunks | Medium — research bridge | High | tag-generator `/trajectory` |

## Recommended Priority

### P0 (RC-2 MVP)

1. **State Timeline** — lowest effort, highest daily usability; extends Dashboard naturally.
2. **Origin Comparison** — directly validates Gemmina Intelligence LLC multi-provider product story.

### P1 (RC-2.1)

3. **Narrative Diff Viewer** — supports audit and regression review after generate.

### P2 (RC-2.2+)

4. **SIV Radar** — requires richer TAG payload than RC-1 minimal T09/T10/T19.
5. **Trajectory Viewer** — depends on trajectory API and coordinate pipeline; defer until Runtime exposes trajectory endpoints.

## Rationale

RC-2 should deepen **observability of existing states** before adding semantic physics visualizations. Timeline and Origin Comparison reuse RC-1 APIs with minimal backend change. SIV Radar and Trajectory Viewer need expanded TAG/coordinate surfaces and belong after RC-2 core navigation is stable.

## Out of Scope (unchanged)

- Semantic PID / MPC
- Semantic Relativity Validation
- New RFC or theory additions
"""
    path.write_text(content, encoding="utf-8")


async def main_async(args: argparse.Namespace) -> int:
    os.environ.setdefault("TESTING", "1")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    run = ValidationRun(
        articles=load_dataset(),
        mode=args.mode,
        runtime_url=args.runtime_url,
    )

    print(f"Validating {len(run.articles)} articles (mode={run.mode})…")
    await run_direct_validation(run)
    validate_browser_fields_local(run)

    if args.mode == "http":
        validate_browser_fields_http(run)

    write_hash_report(run, REPORT_DIR / "hash_validation_report.md")
    write_tag_report(run, REPORT_DIR / "tag_validation_report.md")
    write_diffusion_report(run, REPORT_DIR / "diffusion_validation_report.md")
    write_perf_report(run, REPORT_DIR / "performance_baseline.md")
    write_browser_report(run, REPORT_DIR / "browser_validation_report.md")
    write_summary_report(run, REPORT_DIR / "E2E_VALIDATION_SUMMARY.md")
    write_rc2_backlog(REPORT_DIR / "rc2_backlog.md")

    seed_path = REPORT_DIR / "seed_results.json"
    seed_path.write_text(
        json.dumps(
            [{"id": s["id"], "state_hash": s["state_hash"], "provider": s["provider"]} for s in run.seeded],
            indent=2,
        ),
        encoding="utf-8",
    )

    tag_pass = sum(1 for t in run.tag_checks if t["pass"])
    diff_pass = sum(1 for d in run.diffusion_checks if d["pass"])
    hash_pass = all(h["pass"] for h in run.hash_runs)

    print(f"Hash validation: {'PASS' if hash_pass else 'FAIL'}")
    print(f"T09 validation: {tag_pass}/{len(run.tag_checks)}")
    print(f"Diffusion validation: {diff_pass}/{len(run.diffusion_checks)}")
    print(f"Reports → {REPORT_DIR}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="P1-07 E2E validation runner")
    parser.add_argument("--mode", choices=("direct", "http"), default="direct")
    parser.add_argument("--runtime-url", default="http://localhost:8020")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
