"""Runtime Plugin abstract base and capability descriptors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RuntimeBackend(str, Enum):
    """Supported runtime backend identifiers."""

    CLAUDE_CLI = "claude_cli"
    CLAUDE_API = "claude_api"
    GPT = "gpt"
    GEMINI = "gemini"
    LOCAL_LLM = "local_llm"
    MOCK = "mock"


@dataclass(frozen=True)
class RuntimePluginCapabilities:
    """Describes runtime plugin execution capabilities."""

    backend: RuntimeBackend
    supports_streaming: bool = False
    supports_system_directive: bool = True
    requires_api_key: bool = False
    cli_binary: Optional[str] = None
    model_id: Optional[str] = None
    extra: dict = field(default_factory=dict)


class RuntimePlugin(ABC):
    """
    Pluggable CPU interface. Enables SensOS to run any cognitive core.

    All runtime plugins must implement this contract. Concrete backends
    (Claude CLI, GPT, Gemini, local LLMs) are registered via RuntimePluginRegistry.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Human-readable plugin identifier."""

    @abstractmethod
    def get_capabilities(self) -> RuntimePluginCapabilities:
        """Return structured capability metadata for kernel scheduling."""

    @abstractmethod
    def execute(self, prompt: str, system_directive: str) -> str:
        """
        Execute reasoning over the given prompt under the system directive.

        Returns raw textual output from the cognitive runtime.
        """

    def is_available(self) -> bool:
        """Return True when the plugin can execute requests in the current environment."""
        return True

    def health_check(self) -> dict:
        """Optional health probe for FastAPI integration."""
        return {
            "name": self.get_name(),
            "available": self.is_available(),
            "capabilities": self.get_capabilities().__dict__,
        }
