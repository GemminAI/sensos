"""HEKB MCP tool handlers.

Implements the tool set described in the "HEKB MCP Server Specification"
(Downloads source doc) and RFC-NVS-SEC001/TRUST001, against the REAL
hekb-runtime REST API (EXP-7100) where that API actually supports the
operation, and as an explicit NOT_IMPLEMENTED stub — mirroring the existing
``runtime/mcp/tools.py::LAYER3_STUBS`` pattern already used in this repo —
where it does not. See hekb_mcp/docs/EXPERIMENT_REPORT.md for the full
per-tool accounting.

``observe`` now implements RFC-NVS-0100's NVS.SysObserve: it takes free
natural-language ``text`` and projects it to a semantic coordinate theta
via ``hekb_mcp.observation_engine.ObservationEngine`` (added for RFC-NVS-0100
— see EXPERIMENT_REPORT_RFC0100.md for what this does and doesn't prove
against the RFC's stated thresholds). The previous object_id-based lookup
is still available as ``get_object`` for callers that already hold a known
HEXTObject id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hekb_mcp.client import HekbRuntimeClient, HekbRuntimeError
from hekb_mcp.security import (
    CAP_SYS_NAVIGATE,
    CAP_SYS_OBSERVE,
    CapabilityDenied,
    MeaningFirewallBlocked,
    ObservationTokenIssuer,
    TrustManifestIssuer,
    enforce_geodesic_boundary,
)

if TYPE_CHECKING:
    from hekb_mcp.observation_engine import ObservationEngine

NOT_IMPLEMENTED_TOOLS = {
    "resolve_attractor": (
        "hekb-runtime's QueryEngine has no attractor-ranking primitive — grepped clean for "
        "'attractor'/'basin' in the query layer. FieldImporter can materialize EXP-7000 "
        "AttractorPoints as HEXTObjects (label 'attractor:<id>'), but that path is C++-only, "
        "never exposed over REST, and there is still no server-side 'find nearest/strongest "
        "attractor' query even once such objects exist in storage. This would require new "
        "QueryEngine work, not a client-side wrapper."
    ),
    "find_pullback": (
        "No pullback/pushout (categorical limit/colimit) support exists anywhere in "
        "hekb-runtime — grepped clean. The only multi-object composition primitive is "
        "POST /morphisms/compose (arrow composition A->B, B->C => A->C), which is a "
        "different categorical operation. This would require new engine work."
    ),
}


@dataclass
class ToolContext:
    """Dependency bag for tool handlers — makes tests injectable without monkeypatching."""

    client: HekbRuntimeClient
    token_issuer: ObservationTokenIssuer
    trust_issuer: TrustManifestIssuer
    restricted_object_ids: frozenset[int] = field(default_factory=frozenset)
    observation_engine: "ObservationEngine | None" = None


def _require_capability(ctx: ToolContext, token: str, capability: int) -> None:
    claims = ctx.token_issuer.verify(token)
    claims.require(capability)


def stub_response(tool_name: str) -> dict[str, Any]:
    return {"status": "NOT_IMPLEMENTED", "tool": tool_name, "reason": NOT_IMPLEMENTED_TOOLS[tool_name]}


def get_object(arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    _require_capability(ctx, arguments["token"], CAP_SYS_OBSERVE)
    obj = ctx.client.get_object(int(arguments["object_id"]))
    return {
        "object_id": obj.id,
        "type": obj.type,
        "label": obj.label,
        "potential": obj.potential,
        "energy": obj.energy,
        "curvature": obj.curvature,
        "flux_magnitude": obj.flux_magnitude,
    }


def observe(arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """RFC-NVS-0100 NVS.SysObserve: text -> theta -> HEXT Observation Object."""
    _require_capability(ctx, arguments["token"], CAP_SYS_OBSERVE)
    if ctx.observation_engine is None:
        return {"error": "NVS_ERR_ENGINE_UNAVAILABLE", "message": "ObservationEngine not configured on this ToolContext"}
    result = ctx.observation_engine.observe(arguments["text"])
    return {
        "object_id": result.object_id,
        "chart_id": result.resolution.chart_id,
        "attractor_id": result.resolution.attractor_id,
        "similarity": result.resolution.similarity,
        "resolution_margin": result.resolution.margin,
        "theta_dim": len(result.theta),
        "theta": result.theta,
        "tag_vector_available": result.tag_vector_available,
    }


def follow_geodesic(arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    _require_capability(ctx, arguments["token"], CAP_SYS_NAVIGATE)
    source = int(arguments["from_object_id"])
    target = int(arguments["to_object_id"])
    result = ctx.client.query_geodesic(source, target)
    if result.found:
        # Meaning Firewall enforcement point — RFC-NVS-SEC001 Section 5.
        # Raises MeaningFirewallBlocked (NVS_ERR_FIREWALL_BLOCK) before any
        # path data is returned to the caller if it crosses restricted territory.
        enforce_geodesic_boundary(result.path, ctx.restricted_object_ids)
    return {"found": result.found, "total_cost": result.total_cost, "path": result.path}


def estimate_curvature(arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    _require_capability(ctx, arguments["token"], CAP_SYS_OBSERVE)
    obj = ctx.client.get_object(int(arguments["object_id"]))
    return {
        "object_id": obj.id,
        "curvature": obj.curvature,
        "note": "reads the stored curvature field; hekb-runtime has no curvature ESTIMATION "
        "logic (no computation from graph structure) — this is caller-supplied data, not a "
        "derived estimate.",
    }


def resolve_attractor(arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return stub_response("resolve_attractor")


def find_pullback(arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return stub_response("find_pullback")


def get_trust_manifest(arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    nonce = arguments["nonce"]
    manifest = ctx.trust_issuer.issue(nonce=nonce)
    return manifest.to_dict()


TOOL_HANDLERS = {
    "observe": observe,
    "get_object": get_object,
    "follow_geodesic": follow_geodesic,
    "estimate_curvature": estimate_curvature,
    "resolve_attractor": resolve_attractor,
    "find_pullback": find_pullback,
    "get_trust_manifest": get_trust_manifest,
}


def call_tool(name: str, arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {"error": "UNKNOWN_TOOL", "tool": name}
    try:
        return handler(arguments, ctx)
    except CapabilityDenied as exc:
        return {"error": exc.code, "message": str(exc)}
    except MeaningFirewallBlocked as exc:
        return {"error": exc.code, "message": str(exc), "blocked_object_ids": exc.blocked_object_ids}
    except HekbRuntimeError as exc:
        return {"error": "NVS_ERR_BACKEND_UNAVAILABLE", "message": str(exc)}
    except KeyError as exc:
        return {"error": "NVS_ERR_MISSING_ARGUMENT", "message": f"missing required argument: {exc}"}
