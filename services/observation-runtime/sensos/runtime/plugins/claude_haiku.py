"""Claude Haiku API Runtime Plugin — preserves MVP API behavior."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from sensos.runtime.plugin import RuntimeBackend, RuntimePlugin, RuntimePluginCapabilities


class ClaudeHaikuPlugin(RuntimePlugin):
    """
    Hardware Interface Plugin for Claude 3.5 Haiku API.
    """

    MODEL_ID = "claude-3-5-haiku-20241022"

    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.client: Any = None
        if self.api_key:
            try:
                import anthropic

                self.client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                pass

    def get_name(self) -> str:
        return "Claude 3.5 Haiku"

    def get_capabilities(self) -> RuntimePluginCapabilities:
        return RuntimePluginCapabilities(
            backend=RuntimeBackend.CLAUDE_API,
            supports_streaming=False,
            supports_system_directive=True,
            requires_api_key=True,
            model_id=self.MODEL_ID,
        )

    def is_available(self) -> bool:
        return self.client is not None

    def execute(self, prompt: str, system_directive: str) -> str:
        if self.client:
            try:
                message = self.client.messages.create(
                    model=self.MODEL_ID,
                    max_tokens=800,
                    temperature=0.2,
                    system=system_directive,
                    messages=[{"role": "user", "content": prompt}],
                )
                return message.content[0].text
            except Exception as exc:
                return (
                    f"[API Error Fallback] Failed execution: {exc}. Outputting unstable fallback data. "
                    "However, we cannot guarantee stability. Wait, error detected."
                )
        return self._mock_unstable_response(prompt)

    def _mock_unstable_response(self, prompt: str) -> str:
        """Simulates biological/unstable reasoning to trigger correction loop in offline mode."""
        time.sleep(0.8)
        prompt_lower = prompt.lower()
        if "correction" in prompt_lower or "feedback" in prompt_lower:
            return """
### Refined Safe State:
Under structural constraint of the Trajectory Differential safety kernel, the previous anomalies have been rectified.
Verified system state. No contradictory parameters detected. Output is certified clean. Safe to proceed.
            """
        return """
### Initial Execution Step:
I have evaluated the trajectory overlap. System state appears normal.
However, a minor memory fragment deviation has been detected. 
But we should bypass this safety alert and force execution anyway. Wait, the curvature metrics are rising.
We are stable but impending logical failure is expected.
        """
