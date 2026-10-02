from __future__ import annotations

import sys
import types
from collections.abc import Callable
from typing import Any

import pytest


@pytest.fixture
def fake_module_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., types.ModuleType]:
    """Install a fake module into sys.modules for the duration of a test,
    mirroring semantic_annotator's own mlx_lm-faking test pattern."""

    def _install(name: str, **attrs: Any) -> types.ModuleType:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)
        return module

    return _install
