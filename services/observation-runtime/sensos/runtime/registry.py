"""Runtime plugin registry and factory."""

from __future__ import annotations

from typing import Callable, Dict, Type

from sensos.runtime.plugin import RuntimeBackend, RuntimePlugin
from sensos.runtime.plugins.claude_cli import ClaudeCLIPlugin
from sensos.runtime.plugins.claude_haiku import ClaudeHaikuPlugin
from sensos.runtime.plugins.gemini import GeminiPlugin
from sensos.runtime.plugins.gpt import GPTPlugin
from sensos.runtime.plugins.local_llm import LocalLLMPlugin
from sensos.runtime.plugins.mock_gpt import MockGPTPlugin


PluginFactory = Callable[[], RuntimePlugin]


class RuntimePluginRegistry:
    """
    Central registry for SensOS Runtime Plugins.

    Follows Open/Closed Principle: new backends register without modifying kernel code.
    """

    _factories: Dict[RuntimeBackend, PluginFactory] = {
        RuntimeBackend.CLAUDE_CLI: ClaudeCLIPlugin,
        RuntimeBackend.CLAUDE_API: ClaudeHaikuPlugin,
        RuntimeBackend.GPT: GPTPlugin,
        RuntimeBackend.GEMINI: GeminiPlugin,
        RuntimeBackend.LOCAL_LLM: LocalLLMPlugin,
        RuntimeBackend.MOCK: MockGPTPlugin,
    }

    @classmethod
    def register(cls, backend: RuntimeBackend, factory: PluginFactory) -> None:
        cls._factories[backend] = factory

    @classmethod
    def create(cls, backend: RuntimeBackend) -> RuntimePlugin:
        factory = cls._factories.get(backend)
        if factory is None:
            raise KeyError(f"No runtime plugin registered for backend: {backend}")
        return factory()

    @classmethod
    def create_default(cls) -> RuntimePlugin:
        """
        Resolve the default runtime plugin.

        Priority: Claude CLI → Claude API → Mock (offline simulator).
        """
        cli = ClaudeCLIPlugin()
        if cli.is_available():
            return cli
        api = ClaudeHaikuPlugin()
        if api.is_available():
            return api
        return MockGPTPlugin()

    @classmethod
    def list_backends(cls) -> list[RuntimeBackend]:
        return list(cls._factories.keys())

    @classmethod
    def list_plugins(cls) -> list[RuntimePlugin]:
        return [factory() for factory in cls._factories.values()]
