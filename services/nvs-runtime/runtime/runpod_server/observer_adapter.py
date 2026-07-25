"""Adapter that integrates EXP-Phase27A HiddenStateObserver into the RunPod generation loop."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from observer.hidden_state_observer import HiddenStateObserver, TokenRecord
    from observer.warning import WarningConfig, WarningLevel

_OBSERVER_TYPES: tuple[type, ...] | None = None


def _resolve_exp_src() -> Path:
    env = os.environ.get("NVS_SRC_PATH")
    if not env:
        raise RuntimeError(
            "NVS_SRC_PATH is required for RunPod observer. "
            "Example: NVS_SRC_PATH=/workspace/EXP-Phase27A/src"
        )
    path = Path(env)
    if not path.exists():
        raise RuntimeError(f"NVS_SRC_PATH not found: {path}")
    return path


def _load_observer_types() -> tuple[type, type, type]:
    global _OBSERVER_TYPES
    if _OBSERVER_TYPES is not None:
        return _OBSERVER_TYPES

    exp_src = _resolve_exp_src()
    if str(exp_src) not in sys.path:
        sys.path.insert(0, str(exp_src))

    from observer.hidden_state_observer import HiddenStateObserver, TokenRecord
    from observer.warning import WarningConfig, WarningLevel

    _OBSERVER_TYPES = (HiddenStateObserver, TokenRecord, WarningConfig)
    return _OBSERVER_TYPES


class ObserverAdapter:
    """Thin wrapper around HiddenStateObserver for RunPod inference."""

    def __init__(
        self,
        layers: list[int] | None = None,
        window: int = 32,
        warning_config: Any | None = None,
    ) -> None:
        HiddenStateObserver, _, WarningConfig = _load_observer_types()
        self._config = warning_config or WarningConfig(window=window)
        self._observer = HiddenStateObserver(
            layers=layers or [7, 15, 23, 31],
            window=window,
            warning_config=self._config,
        )
        self._last_token: tuple[int, str] = (0, "")
        self._position: int = 0

    def attach(self, model: Any) -> None:
        self._observer.attach(model)
        self._observer.set_token_callback(lambda: self._last_token)

    def update_token(self, token_id: int, token_text: str) -> None:
        self._last_token = (token_id, token_text)
        self._position += 1

    def records(self) -> list[Any]:
        _, TokenRecord, _ = _load_observer_types()
        return self._observer.records()

    def reset(self) -> None:
        self._observer.reset()
        self._last_token = (0, "")
        self._position = 0

    @property
    def position(self) -> int:
        return self._position

    def detach(self) -> None:
        self._observer.detach()

    def save_jsonl(self, path: Path) -> None:
        self._observer.save_jsonl(path)
