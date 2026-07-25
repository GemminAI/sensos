"""Product JWT/API-key auth (Phase4 MIG-AUTH).

Public symbols match the former ``kernel.runtime.auth`` surface used by hekb_mcp.
"""

from runtime.auth.provider import (
    AuthConfig,
    AuthProvider,
    TokenClaims,
    make_auth_dependency,
    make_scope_checker,
    validate_startup_credentials,
)

__all__ = [
    "AuthConfig",
    "AuthProvider",
    "TokenClaims",
    "make_auth_dependency",
    "make_scope_checker",
    "validate_startup_credentials",
]
