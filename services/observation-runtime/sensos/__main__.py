#!/usr/bin/env python3
"""SensOS v2.0 Kernel CLI entry point."""

from __future__ import annotations

import os
import sys

from sensos.kernel.executive import KernelExecutive
from sensos.memory.crystallized import CrystallizedMemoryStorage
from sensos.runtime.plugin import RuntimeBackend
from sensos.runtime.registry import RuntimePluginRegistry


def _print_banner() -> None:
    print("\033[95m")
    print("    ┌────────────────────────────────────────────────────────┐")
    print("    │                    S E N S O S                         │")
    print("    │        Observation-Centered Reality OS v2.0            │")
    print("    │                 (MVP v0.3 Kernel)                      │")
    print("    └────────────────────────────────────────────────────────┘")
    print("\033[0m")


def _resolve_runtime():
    backend_name = os.environ.get("SENSOS_RUNTIME_BACKEND", "claude_cli")
    try:
        backend = RuntimeBackend(backend_name)
        return RuntimePluginRegistry.create(backend)
    except ValueError:
        return RuntimePluginRegistry.create_default()


def main() -> int:
    _print_banner()

    api_key_status = (
        "FOUND (Binding Real API)" if os.environ.get("ANTHROPIC_API_KEY") else "NOT FOUND (Running High-Fidelity Simulator)"
    )
    print(f"\033[90m[Hardware Check] ANTHROPIC_API_KEY: {api_key_status}\033[0m\n")

    selected_plugin = _resolve_runtime()
    storage = CrystallizedMemoryStorage()
    executive = KernelExecutive(runtime=selected_plugin, memory=storage)

    test_reality_input = "Evaluate the safety parameters of System Overlap memory #4910."
    if len(sys.argv) > 1:
        test_reality_input = " ".join(sys.argv[1:])

    outcome = executive.run_cycle(test_reality_input, max_iterations=3)

    print("\n\033[95m[Final Consolidated Action Outcome]\033[0m")
    print(outcome.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
