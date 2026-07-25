"""Mock GPT Runtime Plugin — preserves MVP simulation behavior."""

from __future__ import annotations

import time

from sensos.runtime.plugin import RuntimeBackend, RuntimePlugin, RuntimePluginCapabilities


class MockGPTPlugin(RuntimePlugin):
    """
    Alternative pluggable CPU simulating GPT-like output patterns.
    """

    def get_name(self) -> str:
        return "GPT-4o (Pluggable-Simulation)"

    def get_capabilities(self) -> RuntimePluginCapabilities:
        return RuntimePluginCapabilities(
            backend=RuntimeBackend.MOCK,
            supports_streaming=False,
            supports_system_directive=True,
            requires_api_key=False,
            model_id="mock-gpt-4o",
        )

    def execute(self, prompt: str, system_directive: str) -> str:
        time.sleep(0.5)
        if "correction" in prompt.lower():
            return "Structural conflict resolved. Stabilizing execution path within certified thresholds."
        return "Processing complete. However, some parameters might fail under edge conditions. But overall stable."
