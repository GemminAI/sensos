"""SensOS Runtime Plugin API — pluggable cognitive CPU interface."""

from sensos.runtime.plugin import RuntimePlugin, RuntimePluginCapabilities
from sensos.runtime.registry import RuntimePluginRegistry

__all__ = ["RuntimePlugin", "RuntimePluginCapabilities", "RuntimePluginRegistry"]
