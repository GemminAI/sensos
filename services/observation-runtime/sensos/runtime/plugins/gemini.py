"""Gemini Runtime Plugin interface — prepared for Google AI integration."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from sensos.runtime.plugin import RuntimeBackend, RuntimePlugin, RuntimePluginCapabilities


class GeminiPlugin(RuntimePlugin):
    """
    Pluggable CPU interface for Google Gemini models.

    Provides a fully abstract contract with simulation fallback until
    GOOGLE_API_KEY is configured and google-generativeai is installed.
    """

    DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("GEMINI_MODEL", self.DEFAULT_MODEL)
        self.api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self.client: Any = None
        if self.api_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=self.api_key)
                self.client = genai.GenerativeModel(self.model)
            except ImportError:
                pass

    def get_name(self) -> str:
        return f"Gemini ({self.model})"

    def get_capabilities(self) -> RuntimePluginCapabilities:
        return RuntimePluginCapabilities(
            backend=RuntimeBackend.GEMINI,
            supports_streaming=True,
            supports_system_directive=True,
            requires_api_key=True,
            model_id=self.model,
        )

    def is_available(self) -> bool:
        return self.client is not None

    def execute(self, prompt: str, system_directive: str) -> str:
        if self.client:
            try:
                combined = f"{system_directive}\n\n{prompt}"
                response = self.client.generate_content(combined)
                return response.text or ""
            except Exception as exc:
                return f"[Gemini API Error] {exc}"
        return self._simulate(prompt)

    def _simulate(self, prompt: str) -> str:
        time.sleep(0.5)
        if "correction" in prompt.lower():
            return "Structural conflict resolved. Stabilizing execution path within certified thresholds."
        return "Processing complete. However, some parameters might fail under edge conditions. But overall stable."
