#!/usr/bin/env python3
"""EXP-5400B Phase 1 health check — Observation Infrastructure only.

Checks (container running + healthy, HTTP where applicable):
  postgres, redis, mock-llm, runtime (sensos-api)

Stdout: JSON object with healthy/unhealthy values.
Exit 0 iff all are healthy.

Stdlib + docker CLI only. No new dependencies.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE = REPO_ROOT / "docker-compose.nvs-runtime.yml"

# health JSON keys → compose service name
SERVICES = {
    "postgres": "postgres",
    "redis": "redis",
    "mock": "mock-llm",
    "runtime": "sensos-api",  # Observation Runtime (Layer Health target)
}

HTTP_CHECKS = {
    "mock": "http://127.0.0.1:8099/health",
    "runtime": "http://127.0.0.1:8090/health",
}


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def container_id(compose_file: Path, service: str) -> str | None:
    result = _run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "ps",
            "-q",
            service,
        ]
    )
    cid = (result.stdout or "").strip()
    return cid or None


def container_running(cid: str) -> bool:
    result = _run(
        ["docker", "inspect", "-f", "{{.State.Running}}", cid]
    )
    return (result.stdout or "").strip().lower() == "true"


def container_health(cid: str) -> str:
    """Return docker Health.Status or 'running' if no healthcheck."""
    result = _run(
        ["docker", "inspect", "-f", "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}", cid]
    )
    status = (result.stdout or "").strip().lower()
    if status in ("", "none"):
        return "running" if container_running(cid) else "unhealthy"
    return status


def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def evaluate(compose_file: Path) -> dict[str, str]:
    report: dict[str, str] = {}
    for key, service in SERVICES.items():
        cid = container_id(compose_file, service)
        if not cid or not container_running(cid):
            report[key] = "unhealthy"
            continue
        health = container_health(cid)
        if health != "healthy" and health != "running":
            report[key] = "unhealthy"
            continue
        if key in HTTP_CHECKS and not http_ok(HTTP_CHECKS[key]):
            report[key] = "unhealthy"
            continue
        # Prefer explicit "healthy" when docker reports it; else healthy if running+HTTP
        report[key] = "healthy"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EXP-5400B Phase 1 health check")
    parser.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--retries", type=int, default=30)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args(argv)

    report: dict[str, str] = {}
    for _ in range(max(1, args.retries)):
        report = evaluate(args.compose)
        if all(v == "healthy" for v in report.values()):
            break
        time.sleep(args.interval)

    print(json.dumps(report, separators=(",", ":")))
    return 0 if all(v == "healthy" for v in report.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
