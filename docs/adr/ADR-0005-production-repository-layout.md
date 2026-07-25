# ADR-0005 — Production repository layout for GemminAI/sensos

| Field | Value |
|-------|-------|
| Status | Accepted |
| Date | 2026-07-25 |
| Supersedes | Layout implied by `nvs-platform-runtime` root packages |

## Context

`nvs-platform-runtime` mixed product services, platform libraries, legacy
kernels, nested OSS trees, and research experiment artifacts. SensOS needs a
commercial integration repository with clear boundaries.

## Decision

Create `GemminAI/sensos` as the production product repository with:

- `services/` for product containers
- `integrations/` for SensOS-side HEKB / MCP adapters (no HEKB core vendoring)
- `interfaces/` for NVS-Kernel ABI / protobuf only
- `compose/` + `deployment/` for orchestration
- Research / experiments / benchmarks excluded by constitution

Gateway and Dashboard are separate containers even when their early
implementations are thin, to preserve long-term topology.

## Consequences

- Algorithms are migrated, not rewritten
- HEKB / HEXT / NVS-Kernel remain external dependencies
- CI validates compose config and forbids HEKB core vendoring paths
- Prior ADRs in this folder may describe historical decisions from the source
  repository; this ADR governs the new tree layout
