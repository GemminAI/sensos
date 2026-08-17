"""Runtime Context — the minimal read-back leg of

    Observation -> MeaningMapper -> Trajectory -> Triangulation ->
    HEKB Evidence -> HEKB Read MCP -> Runtime Context

Given a triangulation summary's HEKB object id (returned by
`runtime.services.capability_decision.request_meaning_triangulation()` as
`evidence_object_id`), assembles what is already persisted in HEKB back
into one plain, JSON-friendly structure: the summary itself, the per-path
trajectory evidence it DERIVES from (found via a real `neighbours()` graph
read, not by re-deriving anything), and their provenance labels.

This module makes no capability-selection or semantic decision of any
kind — it is data assembly only, over the existing HEKB Read MCP client
methods (`runtime.gateway.hekb_client.HekbClient.get_object`/`neighbours`,
Phase 1 of this cycle). It does not decide whether the evidence is "good
enough" to act on; that judgment belongs to whatever calls this, later.

Failure semantics match the rest of this cycle: a HEKB read that fails
(unreachable, transport error) raises — this module never converts an
unavailable dependency into a fabricated empty/successful context.
"""

from __future__ import annotations

from typing import Any

from runtime.gateway.hekb_client import HekbClient


async def get_triangulation_context(
    triangulation_object_id: str, *, hekb: HekbClient | None = None
) -> dict[str, Any]:
    """Reads back a triangulation summary and its DERIVES-linked evidence.

    Returns `{"found": False}` only when the summary object genuinely does
    not exist in HEKB (a real, honest 404 — not raised as an error, same
    convention as `nvs_hekb_get`). Any transport failure while reading
    propagates as an exception, exactly like the Phase 1 Read MCP tools —
    this function does not distinguish "empty context" from "could not
    reach HEKB."
    """
    hekb = hekb or HekbClient()

    summary = await hekb.get_object(triangulation_object_id)
    if summary is None:
        return {"found": False, "triangulation_object_id": triangulation_object_id}

    neighbours = await hekb.neighbours(triangulation_object_id, depth=1)
    related_evidence: list[dict[str, Any]] = []
    for neighbour in neighbours:
        related_object = await hekb.get_object(neighbour["id"])
        if related_object is not None:
            related_evidence.append(
                {
                    "object_id": neighbour["id"],
                    "via_morphism_id": neighbour.get("via"),
                    "hops": neighbour.get("hops"),
                    "object": related_object,
                }
            )

    return {
        "found": True,
        "triangulation_object_id": triangulation_object_id,
        "triangulation": summary,
        "related_evidence": related_evidence,
        "provenance": {
            "triangulation_id": summary.get("labels", {}).get("triangulation_id"),
            "state": summary.get("labels", {}).get("state"),
            "session_id": summary.get("labels", {}).get("session_id"),
            "runtime_cycle_id": summary.get("labels", {}).get("runtime_cycle_id"),
        },
    }
