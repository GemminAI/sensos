"""GPT Runtime Plugin interface — prepared for OpenAI integration."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from sensos.runtime.plugin import RuntimeBackend, RuntimePlugin, RuntimePluginCapabilities


class GPTPlugin(RuntimePlugin):
    """
    Pluggable CPU interface for OpenAI GPT models.

    Provides a fully abstract contract with simulation fallback until
    OPENAI_API_KEY is configured and the openai package is installed.
    """

    DEFAULT_MODEL = "gpt-4o"

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("OPENAI_MODEL", self.DEFAULT_MODEL)
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.client: Any = None
        if self.api_key:
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                pass

    def get_name(self) -> str:
        return f"GPT ({self.model})"

    def get_capabilities(self) -> RuntimePluginCapabilities:
        return RuntimePluginCapabilities(
            backend=RuntimeBackend.GPT,
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
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=800,
                    temperature=0.2,
                    messages=[
                        {"role": "system", "content": system_directive},
                        {"role": "user", "content": prompt},
                    ],
                )
                return response.choices[0].message.content or ""
            except Exception as exc:
                return f"[GPT API Error] {exc}"
        return self._simulate(prompt)

    def _simulate(self, prompt: str) -> str:
        time.sleep(0.5)
        if "correction" in prompt.lower():
            return "Structural conflict resolved. Stabilizing execution path within certified thresholds."
        return "Processing complete. However, some parameters might fail under edge conditions. But overall stable."
