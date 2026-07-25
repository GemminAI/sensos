"""Startup credential validation — template secrets must be fatal."""

from __future__ import annotations

import pytest

from runtime.auth.provider import AuthConfig, validate_startup_credentials


def test_change_me_jwt_secret_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVS_SKIP_STARTUP_VALIDATION", raising=False)
    cfg = AuthConfig(enabled=True, jwt_secret="CHANGE_ME")
    with pytest.raises(SystemExit, match="Default JWT secret detected"):
        validate_startup_credentials(cfg)


def test_generated_jwt_secret_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVS_SKIP_STARTUP_VALIDATION", raising=False)
    cfg = AuthConfig(
        enabled=True,
        jwt_secret="local-dev-only-generated-secret-value-32b",
        api_keys={},
    )
    validate_startup_credentials(cfg)
