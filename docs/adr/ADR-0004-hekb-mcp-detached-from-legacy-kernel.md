> **Historical context** from `nvs-platform-runtime`. Path names may be outdated. Current layout: ADR-0005 + `docs/spec/PRODUCT_BOUNDARY.md`.

# ADR-0004: HEKB MCP detached from Legacy Kernel

| Field | Value |
|-------|-------|
| Status | Accepted |
| Date | 2026-07-25 |
| Constitution | PRODUCT_BOUNDARY §4.5, §7, §11 |
| Related | PHASE3_REPORT, PHASE3_5_REPORT, PHASE4_REPORT |

## Context

`hekb_mcp` (Product) imported Legacy `kernel.runtime.auth` and optionally
`kernel.observer.tag_extractor`, violating the Product → Legacy direction
required by the Product Constitution and ADR-0001.

## Decision

1. JWT `AuthConfig` / `AuthProvider` / `TokenClaims` live under **`runtime/auth`** (Product).
2. 35TAG extraction lives under **`hekb_mcp/tags`** (Product); optional HTTP prefers semantic-annotator.
3. **`hekb_mcp` MUST NOT import the Legacy `kernel` package.**

## Consequences

- Product → Legacy import count for `hekb_mcp` is zero.
- ObservationToken and offline 35TAG golden behavior are preserved (Phase4 verification).
- Legacy `kernel/runtime/auth.py` and `kernel/observer/tag_extractor.py` remain for Internal/Legacy consumers until Deprecation SLA work (MIG-SCRIPTS / Phase5).
- Enables progress toward starting the Deprecation SLA clock on `kernel/` after Internal scripts are cleared.

## Alternatives considered

- Keep importing Legacy behind a permanent facade — rejected (Constitution §7).
- Call Legacy REST `:8080` for auth — rejected (runtime Legacy coupling).
