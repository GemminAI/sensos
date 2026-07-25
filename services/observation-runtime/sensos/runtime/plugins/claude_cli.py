"""Claude CLI Runtime Plugin — first-class SensOS cognitive backend."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

from sensos.runtime.plugin import RuntimeBackend, RuntimePlugin, RuntimePluginCapabilities
from sensos.runtime.plugins.claude_haiku import ClaudeHaikuPlugin


class ClaudeCLIPlugin(RuntimePlugin):
    """
    Hardware Interface Plugin for Anthropic Claude CLI.

    Invokes the `claude` binary for local/agentic reasoning. Falls back to
    ClaudeHaikuPlugin (API) or mock responses when CLI is unavailable.
    """

    DEFAULT_BINARY = "claude"
    DEFAULT_MODEL = "claude-3-5-haiku-20241022"

    def __init__(
        self,
        binary: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = 120,
    ):
        self.binary = binary or os.environ.get("CLAUDE_CLI_BINARY", self.DEFAULT_BINARY)
        self.model = model or os.environ.get("CLAUDE_CLI_MODEL", self.DEFAULT_MODEL)
        self.timeout_seconds = timeout_seconds
        self._api_fallback: Optional[ClaudeHaikuPlugin] = None

    def get_name(self) -> str:
        return f"Claude CLI ({self.model})"

    def get_capabilities(self) -> RuntimePluginCapabilities:
        return RuntimePluginCapabilities(
            backend=RuntimeBackend.CLAUDE_CLI,
            supports_streaming=False,
            supports_system_directive=True,
            requires_api_key=False,
            cli_binary=self.binary,
            model_id=self.model,
        )

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def execute(self, prompt: str, system_directive: str) -> str:
        if self.is_available():
            return self._execute_cli(prompt, system_directive)
        return self._fallback_execute(prompt, system_directive)

    def _execute_cli(self, prompt: str, system_directive: str) -> str:
        combined = f"{system_directive.strip()}\n\n---\n\n{prompt}"
        cmd = [
            self.binary,
            "--print",
            "--model",
            self.model,
            combined,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            error_detail = result.stderr.strip() or f"exit code {result.returncode}"
            return (
                f"[CLI Error Fallback] Failed execution: {error_detail}. "
                "Outputting unstable fallback data. However, we cannot guarantee stability. "
                "Wait, error detected."
            )
        except subprocess.TimeoutExpired:
            return (
                "[CLI Error Fallback] Execution timed out. Outputting unstable fallback data. "
                "However, we cannot guarantee stability. Wait, error detected."
            )
        except Exception as exc:
            return (
                f"[CLI Error Fallback] Failed execution: {exc}. "
                "Outputting unstable fallback data. However, we cannot guarantee stability. "
                "Wait, error detected."
            )

    def _fallback_execute(self, prompt: str, system_directive: str) -> str:
        if self._api_fallback is None:
            self._api_fallback = ClaudeHaikuPlugin()
        if self._api_fallback.is_available():
            return self._api_fallback.execute(prompt, system_directive)
        return self._api_fallback._mock_unstable_response(prompt)
