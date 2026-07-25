#!/usr/bin/env python3
"""Run HEXT STREAM Conformance Test Suite v1.0."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hext_stream.cts.runner import CTSRunner, cts_14_failure_recovery, export_artifacts
from hext_stream.cts.context import RuntimeSession


def main() -> int:
    parser = argparse.ArgumentParser(description="HEXT STREAM CTS v1.0")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
        help="Output directory for reports and CSVs",
    )
    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379/0",
        help="Redis URL for RedisBackend tests",
    )
    parser.add_argument(
        "--http-url",
        default="http://localhost:8030",
        help="HTTP base URL for live docker runtime",
    )
    parser.add_argument(
        "--skip-redis",
        action="store_true",
        help="Skip Redis backend tests",
    )
    parser.add_argument(
        "--skip-http",
        action="store_true",
        help="Skip HTTP docker runtime tests",
    )
    args = parser.parse_args()

    reports: dict[str, object] = {}

    # Backend A: InProcess
    print("[CTS] Running InProcessBackend...")
    s_in = RuntimeSession(backend_name="inprocess")
    try:
        reports["inprocess"] = CTSRunner(s_in).run_all()
    finally:
        s_in.close()

    # Backend B: Redis (direct)
    if not args.skip_redis:
        print("[CTS] Running RedisBackend (direct)...")
        try:
            s_redis = RuntimeSession(backend_name="redis", redis_url=args.redis_url)
            try:
                reports["redis"] = CTSRunner(s_redis).run_all()
                # CTS-14 only meaningful on Redis
                reports["redis"].results.append(cts_14_failure_recovery(args.redis_url))
            finally:
                s_redis.close()
        except Exception as exc:
            print(f"[CTS] Redis backend unavailable: {exc}")

    # HTTP against docker runtime (optional)
    if not args.skip_http:
        print(f"[CTS] Running HTTP runtime at {args.http_url}...")
        try:
            s_http = RuntimeSession(backend_name="http", http_base=args.http_url)
            try:
                h = s_http.health()
                if h.get("status") in {"ok", "healthy"}:
                    reports["http_redis"] = CTSRunner(s_http).run_all()
            finally:
                s_http.close()
        except Exception as exc:
            print(f"[CTS] HTTP runtime unavailable: {exc}")

    export_artifacts(reports, args.output)
    print(f"[CTS] Report written to {args.output / 'CTS_Report.md'}")

    all_pass = all(
        r.passed
        for name, rep in reports.items()
        for r in rep.results
        if name in {"inprocess", "redis"}
    )
    for backend, rep in reports.items():
        passed = sum(1 for r in rep.results if r.passed)
        print(f"  {backend}: {passed}/{len(rep.results)} passed")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
