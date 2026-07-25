#!/usr/bin/env python3
"""Run CTS-20 Processor Extension Conformance Test."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hext_stream.cts.context import RuntimeSession
from hext_stream.cts.cts20_processor import (
    CTS20Runner,
    export_cts20_artifacts,
    run_backend_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="HEXT STREAM CTS-20 Processor Extension")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "results" / "cts20",
        help="Output directory",
    )
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--skip-redis", action="store_true")
    args = parser.parse_args()

    reports: dict = {}

    print("[CTS-20] InProcessBackend...")
    s_in = RuntimeSession(backend_name="inprocess")
    try:
        reports["inprocess"] = CTS20Runner(s_in).run_all()
    finally:
        s_in.close()

    comparison = None
    if not args.skip_redis:
        print("[CTS-20] RedisBackend...")
        try:
            s_redis = RuntimeSession(backend_name="redis", redis_url=args.redis_url)
            try:
                reports["redis"] = CTS20Runner(s_redis).run_all()
            finally:
                s_redis.close()
            comparison = run_backend_comparison(reports["inprocess"], reports["redis"])
            reports["redis"].results.append(comparison)
        except Exception as exc:
            print(f"[CTS-20] Redis unavailable: {exc}")

    export_cts20_artifacts(reports, comparison, args.output)
    print(f"[CTS-20] Report: {args.output / 'processor_report.md'}")

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
