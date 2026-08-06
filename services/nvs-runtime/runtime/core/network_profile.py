"""Network Profile — EXP-Ubuntu011 WAN-aware Runtime transport config.

Loads `config/network_profile.yaml` and selects one profile (local / gcp /
wan — the RFC / EXP-Ubuntu010A-012 canonical names) via the SENSOS_ENV
environment variable. Every outbound leg (NVS/CLE/HEKB) reads its
timeout/retry/batch/pooling behavior from here instead of hardcoding it —
see runtime/gateway/http_pool.py.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel


class NetworkProfile(BaseModel):
    mode: str
    base_rtt_ms: int
    request_timeout_ms: int
    connect_timeout_ms: int
    retry_count: int
    retry_backoff_ms: int
    keep_alive: bool = True
    async_only: bool = True
    batch_size: int = 1
    max_keepalive_connections: int = 20
    max_connections: int = 50


#: nvs-runtime/config/network_profile.yaml, resolved relative to this file
#: rather than the process cwd — robust whether the process starts from
#: nvs-runtime/ (Docker WORKDIR=/app, `uvicorn runtime.main:app`) or from
#: nvs-runtime/runtime/ (`pytest`, matching pytest.ini's own directory).
_SOURCE_TREE_PROFILE_PATH = Path(__file__).resolve().parents[2] / "config" / "network_profile.yaml"

_DEFAULT_PROFILE_PATH_CANDIDATES = (
    os.getenv("NETWORK_PROFILE_PATH", ""),
    str(_SOURCE_TREE_PROFILE_PATH),
    "config/network_profile.yaml",
    "/app/config/network_profile.yaml",
)

#: Backward-compat: "gcp_internal" was this profile's name before RFC /
#: EXP-Ubuntu010A-012 fixed "gcp" as the canonical name. Any pre-existing
#: SENSOS_ENV=gcp_internal (or explicit env_override="gcp_internal") keeps
#: resolving to the "gcp" profile.
_PROFILE_NAME_ALIASES = {"gcp_internal": "gcp"}

_FALLBACK_PROFILE = NetworkProfile(
    mode="local",
    base_rtt_ms=2,
    request_timeout_ms=500,
    connect_timeout_ms=200,
    retry_count=2,
    retry_backoff_ms=50,
)


def _profile_path() -> Path | None:
    for candidate in _DEFAULT_PROFILE_PATH_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def load_network_profile(env_override: str | None = None) -> NetworkProfile:
    """Load the active NetworkProfile.

    Profile selection precedence: `env_override` arg > SENSOS_ENV env var >
    `active_profile` key in the YAML file > "local". If the YAML file is
    missing entirely, falls back to a conservative local-like default rather
    than failing startup — this is transport config, not a hard dependency.
    """
    path = _profile_path()
    if path is None:
        return _FALLBACK_PROFILE

    with path.open() as fh:
        doc = yaml.safe_load(fh) or {}

    profiles = doc.get("profiles", {})
    selected = env_override or os.getenv("SENSOS_ENV") or doc.get("active_profile") or "local"
    selected = _PROFILE_NAME_ALIASES.get(selected, selected)
    raw = profiles.get(selected)
    if raw is None:
        raise ValueError(
            f"network_profile.yaml: unknown profile '{selected}' "
            f"(available: {sorted(profiles)})"
        )
    return NetworkProfile.model_validate(raw)


@lru_cache
def get_network_profile() -> NetworkProfile:
    return load_network_profile()


def reset_network_profile_cache() -> None:
    """Test-only: clear the cached profile so a changed SENSOS_ENV takes effect."""
    get_network_profile.cache_clear()
