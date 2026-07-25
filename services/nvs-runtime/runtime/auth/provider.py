"""
runtime.auth — JWT + API Key Authentication
===========================================

Lifted from ``kernel.runtime.auth`` in Phase4 (MIG-AUTH) without behavior change.
Product code MUST import from ``runtime.auth``, not Legacy ``kernel``.


Supports two authentication schemes:
1. **JWT Bearer tokens** — issued via POST /auth/token
2. **API Keys** — static pre-shared keys in Authorization: ApiKey <key>

Configuration is loaded from ``config/auth.yaml`` or overridden via
environment variables:

    NVS_JWT_SECRET   — JWT signing secret (REQUIRED in production)
    NVS_AUTH_ENABLED — "1" | "0" to enable/disable auth entirely
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional JWT support
# ---------------------------------------------------------------------------
try:
    import jwt as _jwt
    _JWT_AVAILABLE = True
except ImportError:
    _jwt = None  # type: ignore
    _JWT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class TokenClaims:
    """Decoded and validated JWT / API-key claims."""

    subject: str
    scopes: list[str]
    role: str
    token_type: str  # "jwt" | "api_key"
    expires_at: float | None = None

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or "admin" in self.scopes

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


@dataclass
class AuthConfig:
    """Parsed authentication configuration."""

    enabled: bool = True
    jwt_enabled: bool = True
    api_key_enabled: bool = True
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    issuer: str = "nvs-runtime"
    audience: str = "nvs-clients"
    public_paths: list[str] = field(default_factory=lambda: ["/health", "/metrics", "/version", "/docs", "/openapi.json", "/redoc"])
    api_keys: dict[str, dict[str, Any]] = field(default_factory=dict)
    # OAuth2-style client credentials registry: {client_id: {secret_hash, scopes, enabled}}
    clients: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AuthConfig":
        p = Path(path)
        if not p.exists():
            logger.warning("auth.yaml not found at %s — using defaults", p)
            return cls()

        with open(p, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        jwt_cfg = raw.get("jwt", {})
        secret = os.environ.get("NVS_JWT_SECRET") or jwt_cfg.get("secret", "CHANGE_ME_IN_PRODUCTION")
        enabled = os.environ.get("NVS_AUTH_ENABLED", "1").lower() not in ("0", "false", "no")

        api_cfg = raw.get("authentication", {})

        return cls(
            enabled=enabled and bool(raw.get("authentication", {}).get("enabled", True)),
            jwt_enabled=bool(api_cfg.get("jwt_enabled", True)),
            api_key_enabled=bool(api_cfg.get("api_key_enabled", True)),
            jwt_secret=secret,
            jwt_algorithm=jwt_cfg.get("algorithm", "HS256"),
            access_token_expire_minutes=int(jwt_cfg.get("access_token_expire_minutes", 60)),
            refresh_token_expire_days=int(jwt_cfg.get("refresh_token_expire_days", 7)),
            issuer=jwt_cfg.get("issuer", "nvs-runtime"),
            audience=jwt_cfg.get("audience", "nvs-clients"),
            public_paths=api_cfg.get("public_paths", ["/health", "/metrics", "/version", "/docs", "/openapi.json", "/redoc"]),
            api_keys=raw.get("api_keys", {}),
            clients=raw.get("clients", {}),
        )


# ---------------------------------------------------------------------------
# AuthProvider
# ---------------------------------------------------------------------------

class AuthProvider:
    """Main authentication provider.

    Parameters
    ----------
    config : AuthConfig
        Authentication configuration.
    """

    def __init__(self, config: AuthConfig | None = None) -> None:
        self._cfg = config or AuthConfig()
        if not _JWT_AVAILABLE and self._cfg.jwt_enabled:
            logger.warning(
                "PyJWT not installed — JWT auth unavailable. "
                "Install with: pip install pyjwt"
            )

    # ------------------------------------------------------------------
    # Token issuance
    # ------------------------------------------------------------------

    def issue_token(
        self,
        subject: str,
        scopes: list[str],
        role: str = "user",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Issue a JWT access token.

        Parameters
        ----------
        subject : str
            Token subject (client_id or user_id).
        scopes : list[str]
            Granted scopes.
        role : str
            User role.
        extra : dict | None
            Additional claims to embed.

        Returns
        -------
        dict with keys: access_token, token_type, expires_in, scopes
        """
        if not _JWT_AVAILABLE:
            raise RuntimeError("PyJWT is required for JWT token issuance")

        now = time.time()
        expire = now + self._cfg.access_token_expire_minutes * 60

        payload: dict[str, Any] = {
            "sub": subject,
            "iss": self._cfg.issuer,
            "aud": self._cfg.audience,
            "iat": int(now),
            "exp": int(expire),
            "scopes": scopes,
            "role": role,
        }
        if extra:
            payload.update(extra)

        token = _jwt.encode(payload, self._cfg.jwt_secret, algorithm=self._cfg.jwt_algorithm)

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": self._cfg.access_token_expire_minutes * 60,
            "scopes": scopes,
        }

    # ------------------------------------------------------------------
    # Token validation
    # ------------------------------------------------------------------

    def verify_token(self, token: str) -> TokenClaims:
        """Verify a JWT and return claims.

        Raises
        ------
        ValueError
            On any verification failure.
        """
        if not _JWT_AVAILABLE:
            raise RuntimeError("PyJWT is required for JWT verification")

        try:
            payload = _jwt.decode(
                token,
                self._cfg.jwt_secret,
                algorithms=[self._cfg.jwt_algorithm],
                audience=self._cfg.audience,
                issuer=self._cfg.issuer,
                options={"verify_exp": True},
            )
        except Exception as exc:
            raise ValueError(f"Invalid JWT: {exc}") from exc

        return TokenClaims(
            subject=str(payload.get("sub", "")),
            scopes=list(payload.get("scopes", [])),
            role=str(payload.get("role", "user")),
            token_type="jwt",
            expires_at=float(payload.get("exp", 0)),
        )

    def verify_api_key(self, raw_key: str) -> TokenClaims:
        """Verify an API key and return claims.

        Raises
        ------
        ValueError
            If the key is not found or is disabled.
        """
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        for key_id, key_info in self._cfg.api_keys.items():
            if not key_info.get("enabled", True):
                continue
            stored = key_info.get("key_hash", "")
            # Always verify via SHA-256 hash — no dev passthrough allowed
            if (
                stored
                and stored != "placeholder_hash_change_in_production"
                and stored == key_hash
            ):
                return TokenClaims(
                    subject=key_id,
                    scopes=list(key_info.get("scopes", [])),
                    role="api_client",
                    token_type="api_key",
                )

        raise ValueError("API key not found or disabled")

    def verify_client(self, client_id: str, client_secret: str) -> dict[str, Any]:
        """Verify OAuth2-style client credentials and return client info.

        The client registry is read from ``auth.yaml::clients``.
        Secrets are stored as SHA-256 hashes — the plaintext secret is
        never persisted.

        Parameters
        ----------
        client_id:
            Client identifier.
        client_secret:
            Plaintext secret provided by the caller.

        Returns
        -------
        dict
            Client info dict containing at least ``scopes`` and ``enabled``.

        Raises
        ------
        ValueError
            If the client is unknown, disabled, or the secret does not match.
        """
        _PLACEHOLDER_HASHES = {
            "placeholder_secret_hash_change_in_production",
            "placeholder_hash_change_in_production",
        }

        client = self._cfg.clients.get(client_id)
        if client is None:
            raise ValueError("Unknown client_id")
        if not client.get("enabled", True):
            raise ValueError("Client is disabled")

        stored_hash = client.get("secret_hash", "")
        if not stored_hash or stored_hash in _PLACEHOLDER_HASHES:
            raise ValueError(
                "Client secret not configured. "
                "Set a proper secret_hash in auth.yaml before use."
            )

        provided_hash = hashlib.sha256(client_secret.encode()).hexdigest()
        if stored_hash != provided_hash:
            raise ValueError("Invalid client_secret")

        return client

    def authenticate(self, authorization: str | None) -> TokenClaims | None:
        """Parse and verify an Authorization header.

        Supports:
        - ``Bearer <jwt>``
        - ``ApiKey <key>``

        Returns None if authentication is disabled.
        Raises ValueError on invalid credentials.
        """
        if not self._cfg.enabled:
            return None

        if not authorization:
            raise ValueError("Missing Authorization header")

        parts = authorization.split(" ", 1)
        if len(parts) != 2:
            raise ValueError("Invalid Authorization header format")

        scheme, credential = parts[0].lower(), parts[1].strip()

        if scheme == "bearer" and self._cfg.jwt_enabled:
            return self.verify_token(credential)

        if scheme == "apikey" and self._cfg.api_key_enabled:
            return self.verify_api_key(credential)

        raise ValueError(f"Unsupported auth scheme: {parts[0]!r}")

    def is_public_path(self, path: str) -> bool:
        """Return True if the path is exempt from authentication."""
        return path in self._cfg.public_paths


# ---------------------------------------------------------------------------
# FastAPI dependency factories
# ---------------------------------------------------------------------------

def make_auth_dependency(provider: "AuthProvider"):
    """Build a FastAPI dependency that validates every request."""
    from fastapi import Request, HTTPException, status

    async def _auth(request: Request) -> TokenClaims | None:
        if not provider._cfg.enabled or provider.is_public_path(request.url.path):
            return None
        header = request.headers.get("Authorization")
        try:
            return provider.authenticate(header)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    return _auth


def make_scope_checker(provider: "AuthProvider", required_scope: str):
    """Build a FastAPI dependency that enforces a specific scope."""
    from fastapi import Request, HTTPException, status

    async def _check(request: Request) -> TokenClaims | None:
        if not provider._cfg.enabled:
            return None
        header = request.headers.get("Authorization")
        try:
            claims = provider.authenticate(header)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        if claims and not claims.has_scope(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Scope '{required_scope}' required",
            )
        return claims

    return _check


# ---------------------------------------------------------------------------
# Startup credential validation (B03)
# ---------------------------------------------------------------------------

_PLACEHOLDER_JWT_SECRETS = frozenset({
    "CHANGE_ME_IN_PRODUCTION",
    "change_me_in_production",
    "changeme",
    "",
})

_PLACEHOLDER_KEY_HASHES = frozenset({
    "placeholder_hash_change_in_production",
    "placeholder_admin_hash_change_in_production",
    "placeholder_secret_hash_change_in_production",
})


def validate_startup_credentials(cfg: AuthConfig) -> None:
    """Refuse application startup if production credentials are still placeholders.

    Bypassed by setting ``NVS_SKIP_STARTUP_VALIDATION=1``.
    Never set that variable in a real production environment.

    Raises
    ------
    RuntimeError
        If ``jwt_secret`` is a known placeholder and auth is enabled.
    """
    if os.environ.get("NVS_SKIP_STARTUP_VALIDATION", "").lower() in ("1", "true", "yes"):
        logger.warning(
            "NVS_SKIP_STARTUP_VALIDATION is set — credential check bypassed. "
            "Do NOT use this in production."
        )
        return

    if not cfg.enabled:
        return

    if cfg.jwt_secret in _PLACEHOLDER_JWT_SECRETS:
        raise RuntimeError(
            "SECURITY STARTUP FAILURE: JWT secret is still the default placeholder "
            "('CHANGE_ME_IN_PRODUCTION'). "
            "Set the NVS_JWT_SECRET environment variable to a cryptographically "
            "random secret (>= 32 bytes) before starting the server."
        )

    # Warn (not error) when all API keys still use placeholder hashes.
    enabled_keys = {k: v for k, v in cfg.api_keys.items() if v.get("enabled", True)}
    all_placeholder = enabled_keys and all(
        v.get("key_hash", "") in _PLACEHOLDER_KEY_HASHES
        for v in enabled_keys.values()
    )
    if all_placeholder:
        logger.warning(
            "All API key hashes are still placeholders. "
            "Replace them with SHA-256 hashes of real secrets before production use."
        )
