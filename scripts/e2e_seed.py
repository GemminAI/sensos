#!/usr/bin/env python3
"""Seed narrative states from E2E sample articles via POST /runtime/generate."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from e2e_db import make_sqlite_session

DATASET = ROOT / "tests" / "e2e" / "sample_articles.json"
DEFAULT_RUNTIME = "http://localhost:8020"


def load_dataset(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def seed_http(runtime_url: str, articles: list[dict], *, dry_run: bool = False) -> list[dict]:
    results: list[dict] = []
    url = f"{runtime_url.rstrip('/')}/runtime/generate"

    with httpx.Client(timeout=120.0) as client:
        health = client.get(f"{runtime_url.rstrip('/')}/health")
        health.raise_for_status()

        for item in articles:
            payload = {"article": item["article"], "origin": item["origin"]}
            if dry_run:
                print(f"[dry-run] POST {url} id={item['id']} origin={item['origin']}")
                continue

            t0 = time.perf_counter()
            resp = client.post(url, json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            resp.raise_for_status()
            data = resp.json()
            row = {
                "id": item["id"],
                "category": item["category"],
                "state_hash": data["state_hash"],
                "provider": data["provider"],
                "elapsed_ms": round(elapsed_ms, 1),
            }
            results.append(row)
            print(f"✓ {item['id']} → {data['state_hash'][:16]}… ({elapsed_ms:.0f}ms)")

    return results


def seed_direct(articles: list[dict]) -> list[dict]:
    """Seed via in-process pipeline (no HTTP server required)."""
    import asyncio

    from runtime.services.pipeline import NarrativePipeline

    Session = make_sqlite_session()
    pipeline = NarrativePipeline()
    results: list[dict] = []

    async def _run_all() -> None:
        for item in articles:
            session = Session()
            try:
                t0 = time.perf_counter()
                data = await pipeline.run(session, item["article"], origin=item["origin"])
                session.commit()
                elapsed_ms = (time.perf_counter() - t0) * 1000
                row = {
                    "id": item["id"],
                    "category": item["category"],
                    "state_hash": data["state_hash"],
                    "provider": data["provider"],
                    "elapsed_ms": round(elapsed_ms, 1),
                }
                results.append(row)
                print(f"✓ {item['id']} → {data['state_hash'][:16]}… ({elapsed_ms:.0f}ms)")
            finally:
                session.close()

    asyncio.run(_run_all())
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E seeder for Browser RC-1")
    parser.add_argument("--runtime-url", default=DEFAULT_RUNTIME)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--mode", choices=("http", "direct"), default="http")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "e2e" / "seed_results.json")
    args = parser.parse_args()

    articles = load_dataset(args.dataset)
    print(f"Loaded {len(articles)} articles from {args.dataset}")

    if args.mode == "direct":
        results = seed_direct(articles) if not args.dry_run else []
    else:
        try:
            results = seed_http(args.runtime_url, articles, dry_run=args.dry_run)
        except httpx.HTTPError as exc:
            print(f"HTTP seed failed: {exc}", file=sys.stderr)
            print("Tip: start runtime or use --mode direct", file=sys.stderr)
            return 1

    if results and not args.dry_run:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Saved {len(results)} results → {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
