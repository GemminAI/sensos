"""Local LLM Runtime Plugin interface — prepared for Ollama / llama.cpp."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional

from sensos.runtime.plugin import RuntimeBackend, RuntimePlugin, RuntimePluginCapabilities


class LocalLLMPlugin(RuntimePlugin):
    """
    Pluggable CPU interface for local inference servers (Ollama-compatible).

    Uses the Ollama HTTP API by default. Configure via LOCAL_LLM_BASE_URL and
    LOCAL_LLM_MODEL environment variables.
    """

    DEFAULT_BASE_URL = "http://127.0.0.1:11434"
    DEFAULT_MODEL = "llama3.2"

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = 120,
    ):
        self.base_url = (base_url or os.environ.get("LOCAL_LLM_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.model = model or os.environ.get("LOCAL_LLM_MODEL", self.DEFAULT_MODEL)
        self.timeout_seconds = timeout_seconds

    def get_name(self) -> str:
        return f"Local LLM ({self.model} @ {self.base_url})"

    def get_capabilities(self) -> RuntimePluginCapabilities:
        return RuntimePluginCapabilities(
            backend=RuntimeBackend.LOCAL_LLM,
            supports_streaming=True,
            supports_system_directive=True,
            requires_api_key=False,
            model_id=self.model,
            extra={"base_url": self.base_url},
        )

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def execute(self, prompt: str, system_directive: str) -> str:
        if self.is_available():
            return self._execute_ollama(prompt, system_directive)
        return self._simulate(prompt)

    def _execute_ollama(self, prompt: str, system_directive: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_directive},
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                message = body.get("message", {})
                return message.get("content", "")
        except Exception as exc:
            return f"[Local LLM Error] {exc}"

    def _simulate(self, prompt: str) -> str:
        time.sleep(0.5)
        if "correction" in prompt.lower():
            return "Structural conflict resolved. Stabilizing execution path within certified thresholds."
        return "Processing complete. However, some parameters might fail under edge conditions. But overall stable."
