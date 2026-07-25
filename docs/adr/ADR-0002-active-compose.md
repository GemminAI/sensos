> **Historical context** from `nvs-platform-runtime`. Path names may be outdated. Current layout: ADR-0005 + `docs/spec/PRODUCT_BOUNDARY.md`.

# ADR-0002: Active Compose

| Field | Value |
|-------|-------|
| Status | Accepted |
| Date | 2026-07-25 |
| Constitution | PRODUCT_BOUNDARY §9, §11, §20 |

## Context

Multiple compose/Dockerfile trains existed (`docker-compose.nvs-runtime.yml`, `docker-compose.sensos.yml`, legacy `docker-compose.yml` / Phase37-C). Default orchestration was ambiguous for agents and operators.

## Decision

**Active product release train is `docker-compose.nvs-runtime.yml`.**

`docker-compose.sensos.yml` remains allowed for SensOS-only bring-up.

Legacy `docker-compose.yml` and duplicate Dockerfiles are **Deprecated** / Archive Candidates; they MUST NOT be restored as the default train.

## Consequences

- Makefile and CI product paths SHOULD target the Active compose.
- Image tags for Release Units follow PRODUCT_BOUNDARY §9.
- Changing the Active train requires a new ADR and a constitution bump.

## Alternatives considered

- Treat all compose files as equal — rejected (no single release train).
- SensOS-only compose as sole Active train — rejected (integrated product includes Runtime/HEXT/HEKB/Annotator).
