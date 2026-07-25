#!/usr/bin/env python3
"""Run CTS-17 Morphism Lineage Conformance Test."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hext_stream.cts.context import RuntimeSession
from hext_stream.cts.cts17_lineage import (
    CTS17Runner,
    export_cts17_artifacts,
    run_backend_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="HEXT STREAM CTS-17 Lineage Conformance")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "results" / "cts17",
        help="Output directory",
    )
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--skip-redis", action="store_true")
    args = parser.parse_args()

    reports = {}

    print("[CTS-17] InProcessBackend...")
    s_in = RuntimeSession(backend_name="inprocess")
    try:
        reports["inprocess"] = CTS17Runner(s_in).run_all()
    finally:
        s_in.close()

    comparison = None
    if not args.skip_redis:
        print("[CTS-17] RedisBackend...")
        try:
            s_redis = RuntimeSession(backend_name="redis", redis_url=args.redis_url)
            try:
                reports["redis"] = CTS17Runner(s_redis).run_all()
            finally:
                s_redis.close()
            comparison = run_backend_comparison(reports["inprocess"], reports["redis"])
            reports["redis"].results.append(comparison)
        except Exception as exc:
            print(f"[CTS-17] Redis unavailable: {exc}")

    export_cts17_artifacts(reports, comparison, args.output)
    print(f"[CTS-17] Report: {args.output / 'lineage_report.md'}")

    all_pass = all(
        r.passed
        for name in ("inprocess", "redis")
        if name in reports
        for r in reports[name].results
    )
    for name, rep in reports.items():
        p = sum(1 for r in rep.results if r.passed)
        print(f"  {name}: {p}/{len(rep.results)} passed")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
