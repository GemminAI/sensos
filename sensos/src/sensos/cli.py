"""sensos CLI entry point: `sensos doctor`, `sensos smoke`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from sensos.doctor import CheckResult, run_doctor
from sensos.smoke import SmokeResult, run_smoke


def print_doctor_results(results: Sequence[CheckResult], stream: TextIO) -> bool:
    all_passed = True
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        if not result.passed:
            all_passed = False
        stream.write(f"[{status}] {result.name}: {result.detail}\n")
    return all_passed


def print_smoke_result(result: SmokeResult, stream: TextIO) -> None:
    status = "PASS" if result.passed else "FAIL"
    stream.write(f"[{status}] {result.stage}: {result.detail}\n")


def run_doctor_command(stream: TextIO) -> int:
    results = run_doctor()
    all_passed = print_doctor_results(results, stream)
    return 0 if all_passed else 1


def run_smoke_command(
    stream: TextIO, *, base_url: str | None = None, model: str | None = None
) -> int:
    result = run_smoke(base_url=base_url, model=model)
    print_smoke_result(result, stream)
    return 0 if result.passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sensos", description="SensOS Runtime CLI (doctor, smoke)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check environment and dependencies (no model load)")

    smoke_parser = subparsers.add_parser(
        "smoke", help="Run a minimal, real RuntimeBridge -> vLLM -> LLMAnnotator smoke test"
    )
    smoke_parser.add_argument(
        "--runtime-bridge-url",
        default=None,
        help="vLLM server base URL (default: $RUNTIME_BRIDGE_URL)",
    )
    smoke_parser.add_argument(
        "--model", default=None, help="Model being served by vLLM (default: $SENSOS_MODEL_ID)"
    )

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        exit_code = run_doctor_command(sys.stdout)
    elif args.command == "smoke":
        exit_code = run_smoke_command(
            sys.stdout, base_url=args.runtime_bridge_url, model=args.model
        )
    else:  # pragma: no cover - argparse enforces valid choices via subparsers
        parser.error(f"unknown command: {args.command}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
