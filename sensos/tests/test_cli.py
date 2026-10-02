from __future__ import annotations

import io

import pytest

from sensos.cli import (
    build_parser,
    print_doctor_results,
    print_smoke_result,
    run_doctor_command,
    run_smoke_command,
)
from sensos.doctor import CheckResult
from sensos.smoke import SmokeResult


def test_print_doctor_results_all_pass_returns_true() -> None:
    stream = io.StringIO()
    results = [CheckResult("OS", True, "Linux"), CheckResult("Python", True, "3.12.5")]

    all_passed = print_doctor_results(results, stream)

    assert all_passed is True
    output = stream.getvalue()
    assert "[PASS] OS: Linux" in output
    assert "[PASS] Python: 3.12.5" in output


def test_print_doctor_results_any_fail_returns_false() -> None:
    stream = io.StringIO()
    results = [
        CheckResult("OS", True, "Linux"),
        CheckResult("Inference backend (vLLM)", False, "vllm not installed"),
    ]

    all_passed = print_doctor_results(results, stream)

    assert all_passed is False
    assert "[FAIL] Inference backend (vLLM): vllm not installed" in stream.getvalue()


def test_print_smoke_result_pass() -> None:
    stream = io.StringIO()
    print_smoke_result(SmokeResult(True, "AnnotatedObservation", "1 annotation(s)"), stream)
    assert "[PASS] AnnotatedObservation: 1 annotation(s)" in stream.getvalue()


def test_print_smoke_result_fail() -> None:
    stream = io.StringIO()
    print_smoke_result(SmokeResult(False, "configuration", "RUNTIME_BRIDGE_URL is not set"), stream)
    assert "[FAIL] configuration: RUNTIME_BRIDGE_URL is not set" in stream.getvalue()


def test_run_doctor_command_exit_code_reflects_overall_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sensos.cli.run_doctor",
        lambda: [CheckResult("OS", True, "Linux"), CheckResult("uv", False, "not found")],
    )
    stream = io.StringIO()

    exit_code = run_doctor_command(stream)

    assert exit_code == 1
    assert "[FAIL] uv: not found" in stream.getvalue()


def test_run_doctor_command_exit_code_zero_when_all_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sensos.cli.run_doctor", lambda: [CheckResult("OS", True, "Linux")])
    stream = io.StringIO()

    exit_code = run_doctor_command(stream)

    assert exit_code == 0


def test_run_smoke_command_exit_code_reflects_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sensos.cli.run_smoke",
        lambda **kwargs: SmokeResult(False, "configuration", "RUNTIME_BRIDGE_URL is not set"),
    )
    stream = io.StringIO()

    exit_code = run_smoke_command(stream)

    assert exit_code == 1
    assert "RUNTIME_BRIDGE_URL is not set" in stream.getvalue()


def test_build_parser_doctor_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(["doctor"])
    assert args.command == "doctor"


def test_build_parser_smoke_subcommand_with_options() -> None:
    parser = build_parser()
    args = parser.parse_args(["smoke", "--runtime-bridge-url", "http://x:8000", "--model", "m"])
    assert args.command == "smoke"
    assert args.runtime_bridge_url == "http://x:8000"
    assert args.model == "m"


def test_build_parser_requires_a_command() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
