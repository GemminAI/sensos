"""Tests for Runtime Plugin API."""

from sensos.runtime.plugin import RuntimeBackend
from sensos.runtime.plugins.claude_haiku import ClaudeHaikuPlugin
from sensos.runtime.plugins.mock_gpt import MockGPTPlugin
from sensos.runtime.registry import RuntimePluginRegistry


def test_registry_lists_all_backends():
    backends = RuntimePluginRegistry.list_backends()
    assert RuntimeBackend.CLAUDE_CLI in backends
    assert RuntimeBackend.GPT in backends
    assert RuntimeBackend.GEMINI in backends
    assert RuntimeBackend.LOCAL_LLM in backends


def test_mock_gpt_correction_branch(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    plugin = MockGPTPlugin()
    out = plugin.execute("please apply correction", "directive")
    assert "Structural conflict resolved" in out


def test_claude_haiku_offline_mock(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    plugin = ClaudeHaikuPlugin()
    assert not plugin.is_available()
    out = plugin.execute("initial", "directive")
    assert "However" in out


def test_plugin_capabilities_metadata():
    plugin = MockGPTPlugin()
    caps = plugin.get_capabilities()
    assert caps.backend == RuntimeBackend.MOCK
