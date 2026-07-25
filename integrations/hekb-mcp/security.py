"""Security layer for hekb_mcp: ObservationToken, Meaning Firewall, TrustManifest.

Implementation status (see hekb_mcp/docs/EXPERIMENT_REPORT.md for the full
account): this module implements the Generation-2 concepts from
RFC-NVS-SEC001 (Meaning Firewall) and RFC-NVS-TRUST001 (Trust Manifest) as
an experimental, SOFTWARE-ONLY simulation:

- ObservationToken reuses Product JWT infrastructure
  (``runtime.auth.AuthProvider``, Phase4 MIG-AUTH) rather than reimplementing
  token signing/verification. It adds a ``capabilities`` bitmask claim on top.
- The Meaning Firewall check here is a GRAPH-MEMBERSHIP approximation of
  SEC001 Section 5.1's manifold-distance boundary
  (``||theta(s) - A_restricted|| <= B_restricted``). hekb-runtime's REST API
  exposes no embedding-space coordinates for any HEXTObject (only scalar
  potential/energy/curvature/flux_magnitude — confirmed by direct inspection
  of rest_server.cpp), so a true Euclidean/geodesic-metric distance to a
  restricted region's center cannot be computed from this client. This
  checks graph-node membership in a configured restricted-id set instead,
  which is a real but weaker guarantee than the spec describes.
- TrustManifest issuance here has NO TPM 2.0, NO PCR measurement, and NO
  hardware anchor of trust. It is a locally HMAC-signed JSON document
  suitable for validating the *shape* and *signing/verification workflow*
  described in TRUST001, not for any real attestation claim. Fields that
  would require hardware are explicitly set to "NOT_AVAILABLE_SOFTWARE_SIMULATION"
  rather than fabricated.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import jwt as _pyjwt

from runtime.auth import AuthConfig, AuthProvider

DEFAULT_AUTH_CONFIG_PATH = Path(__file__).parent / "config" / "auth.yaml"

# ---------------------------------------------------------------------------
# Capability bitmask — RFC-NVS-SEC001 Section 4.1
# ---------------------------------------------------------------------------

CAP_SYS_OBSERVE = 0x01  # READ ONLY — text -> ObservationObject / coordinates
CAP_SYS_NAVIGATE = 0x02  # EXECUTABLE ONLY — follow a verified geodesic
CAP_SYS_RENDER = 0x04  # NO DATABASE ACCESS — read RenderResult metadata only

CAPABILITY_NAMES = {
    CAP_SYS_OBSERVE: "sys_observe",
    CAP_SYS_NAVIGATE: "sys_navigate",
    CAP_SYS_RENDER: "sys_render",
}


class NVSError(RuntimeError):
    """Base class for NVS_ERR_* conditions, carrying the spec's error code string."""

    code: str = "NVS_ERR_UNKNOWN"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)


class CapabilityDenied(NVSError):
    code = "NVS_ERR_CAPABILITY_DENIED"


class MeaningFirewallBlocked(NVSError):
    code = "NVS_ERR_FIREWALL_BLOCK"

    def __init__(self, blocked_object_ids: list[int]) -> None:
        self.blocked_object_ids = blocked_object_ids
        super().__init__(f"{self.code}: path enters restricted object ids {blocked_object_ids}")


# ---------------------------------------------------------------------------
# ObservationToken
# ---------------------------------------------------------------------------


@dataclass
class ObservationTokenClaims:
    subject: str
    capabilities: int
    role: str
    expires_at: float | None

    def has_capability(self, capability: int) -> bool:
        return bool(self.capabilities & capability)

    def require(self, capability: int) -> None:
        if not self.has_capability(capability):
            name = CAPABILITY_NAMES.get(capability, hex(capability))
            raise CapabilityDenied(f"NVS_ERR_CAPABILITY_DENIED: token lacks capability {name}")


class ObservationTokenIssuer:
    """Issues and verifies ObservationTokens on top of the existing AuthProvider."""

    def __init__(self, config_path: str | Path = DEFAULT_AUTH_CONFIG_PATH) -> None:
        self._auth_config = AuthConfig.from_yaml(config_path)
        self._auth = AuthProvider(self._auth_config)

    def issue(self, subject: str, capabilities: int, role: str = "observer") -> str:
        scopes = [name for bit, name in CAPABILITY_NAMES.items() if capabilities & bit]
        result = self._auth.issue_token(subject=subject, scopes=scopes, role=role, extra={"capabilities": capabilities})
        return result["access_token"]

    def verify(self, token: str) -> ObservationTokenClaims:
        # AuthProvider.verify_token performs the actual signature/exp/iss/aud
        # validation and raises ValueError on any failure; we only re-decode
        # the already-validated payload to pull out the extra `capabilities`
        # claim it does not itself surface on TokenClaims.
        claims = self._auth.verify_token(token)
        payload = _pyjwt.decode(
            token,
            self._auth_config.jwt_secret,
            algorithms=[self._auth_config.jwt_algorithm],
            audience=self._auth_config.audience,
            issuer=self._auth_config.issuer,
        )
        return ObservationTokenClaims(
            subject=claims.subject,
            capabilities=int(payload.get("capabilities", 0)),
            role=claims.role,
            expires_at=claims.expires_at,
        )


# ---------------------------------------------------------------------------
# Meaning Firewall — graph-membership approximation (see module docstring)
# ---------------------------------------------------------------------------


@dataclass
class FirewallCheckResult:
    blocked: bool
    blocked_object_ids: list[int] = field(default_factory=list)


def check_geodesic_boundary(path: list[int], restricted_object_ids: frozenset[int]) -> FirewallCheckResult:
    """Check whether a geodesic path (list of HEXTObject ids) enters restricted territory.

    This is a graph-membership check, not a manifold-distance check — see
    module docstring for why. A path is blocked if ANY object id it visits
    is a member of ``restricted_object_ids``.
    """
    hits = [oid for oid in path if oid in restricted_object_ids]
    return FirewallCheckResult(blocked=bool(hits), blocked_object_ids=hits)


def enforce_geodesic_boundary(path: list[int], restricted_object_ids: frozenset[int]) -> None:
    """Raise MeaningFirewallBlocked if the path enters restricted territory."""
    result = check_geodesic_boundary(path, restricted_object_ids)
    if result.blocked:
        raise MeaningFirewallBlocked(result.blocked_object_ids)


# ---------------------------------------------------------------------------
# TrustManifest — software simulation (see module docstring)
# ---------------------------------------------------------------------------

NOT_AVAILABLE = "NOT_AVAILABLE_SOFTWARE_SIMULATION"


@dataclass
class SimulatedTrustManifest:
    manifest_magic: str
    manifest_version: str
    timestamp_ms: int
    kernel_release: str
    run_level_mode: str
    semantic_compliance_mask: int
    nonce_feedback: str
    sbom_hash: str
    tpm_pcr_quote: str
    approved_policy_manifest_hash: str
    approved_weight_manifest_hash: str
    signature: str

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_magic": self.manifest_magic,
            "manifest_version": self.manifest_version,
            "timestamp_ms": self.timestamp_ms,
            "kernel_release": self.kernel_release,
            "run_level_mode": self.run_level_mode,
            "semantic_compliance_mask": self.semantic_compliance_mask,
            "nonce_feedback": self.nonce_feedback,
            "sbom_hash": self.sbom_hash,
            "tpm_pcr_quote": self.tpm_pcr_quote,
            "approved_policy_manifest_hash": self.approved_policy_manifest_hash,
            "approved_weight_manifest_hash": self.approved_weight_manifest_hash,
            "signature": self.signature,
        }


class TrustManifestIssuer:
    """Issues and verifies a software-simulated TrustManifest via HMAC-SHA256.

    No TPM. No PCR measurement. No hardware anchor of trust. See module
    docstring. Signing key is the same JWT secret used by ObservationToken
    issuance for this experimental package — a real Level 3 (ENTERPRISE)
    implementation per RFC-NVS-0001 Section 3.3 would require a TPM AIK or
    KMS-backed asymmetric key, not a shared HMAC secret.
    """

    def __init__(self, config_path: str | Path = DEFAULT_AUTH_CONFIG_PATH, kernel_release: str = "hekb_mcp-0.1.0-experimental") -> None:
        self._auth_config = AuthConfig.from_yaml(config_path)
        self._kernel_release = kernel_release

    def issue(self, nonce: str, semantic_compliance_mask: int = 0) -> SimulatedTrustManifest:
        payload = {
            "manifest_magic": "SOST",
            "manifest_version": "3.0.0-sim",
            "timestamp_ms": int(time.time() * 1000),
            "kernel_release": self._kernel_release,
            "run_level_mode": "SIMULATED_LEVEL_0_MONITOR",
            "semantic_compliance_mask": semantic_compliance_mask,
            "nonce_feedback": nonce,
            "sbom_hash": NOT_AVAILABLE,
            "tpm_pcr_quote": NOT_AVAILABLE,
            "approved_policy_manifest_hash": NOT_AVAILABLE,
            "approved_weight_manifest_hash": NOT_AVAILABLE,
        }
        signature = _pyjwt.encode(payload, self._auth_config.jwt_secret, algorithm="HS256")
        return SimulatedTrustManifest(**payload, signature=signature)

    def verify(self, manifest: SimulatedTrustManifest) -> bool:
        try:
            _pyjwt.decode(manifest.signature, self._auth_config.jwt_secret, algorithms=["HS256"])
        except Exception:
            return False
        return True
