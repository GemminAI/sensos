> **Historical context** from `nvs-platform-runtime`. Path names may be outdated. Current layout: ADR-0005 + `docs/spec/PRODUCT_BOUNDARY.md`.

# ADR-0003: HEKB Dual Architecture

| Field | Value |
|-------|-------|
| Status | Accepted |
| Date | 2026-07-25 |
| Constitution | PRODUCT_BOUNDARY §4.4, §5, §11 |

## Context

Two HEKB implementations coexist:

| Path | Stack | Role |
|------|-------|------|
| `hekb/` | Python / FastAPI | Projection Runtime; Active compose service `hekb-projection` |
| `hekb-runtime/` | C++20 / LMDB | Knowledge runtime; Platform / EXP-7100 reference lineage |

Package naming currently collides (`hekb/pyproject.toml` name `hekb-runtime`). Canonical long-term binary is not yet chosen.

## Decision

**Dual architecture is permitted temporarily under explicit roles:**

1. **Product face (compose):** `hekb/` (HEKB Projection).
2. **Platform / successor candidate:** `hekb-runtime/` (C++).
3. **No third HEKB runtime** may be introduced.
4. **No silent swap** of Active compose wiring between the two without a superseding ADR and constitution update.
5. A future ADR MUST select a single canonical HEKB Release Unit and resolve naming.

## Consequences

- Product integrations default to `hekb/` APIs on the Active train.
- C++ stack continues as Platform under the estimation DAG (`exp6000`→…→`hekb-runtime`→`trajectory-engine`).
- Ownership: both rows remain in PRODUCT_BOUNDARY §30 until canonicalization.

## Alternatives considered

- Immediate deletion of one stack — rejected (evaluation incomplete; data/API risk).
- Merge trees now — rejected (premature; requires dedicated migration ADR).
