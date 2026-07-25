> **Historical context** from `nvs-platform-runtime`. Path names may be outdated. Current layout: ADR-0005 + `docs/spec/PRODUCT_BOUNDARY.md`.

# ADR-0001: Canonical Kernel = sensos

| Field | Value |
|-------|-------|
| Status | Accepted |
| Date | 2026-07-25 |
| Constitution | PRODUCT_BOUNDARY §4.1, §7, §11 |

## Context

The repository contained two kernel-shaped stacks: `sensos/` (declared production-quality Observation OS) and `kernel/` (historical NVS-Kernel / DAK observation stack). Parallel feature work would fork the product.

## Decision

**Canonical Product Kernel is `sensos/`.**

`kernel/` is **Legacy**: no new features; caretaker fixes only until Deprecation SLA retirement.

## Consequences

- New observation/kernel capability MUST land in `sensos/`.
- Agents and developers MUST NOT extend `kernel/api` or `kernel/core` for product work.
- Migration of remaining dependents off `kernel/` is tracked under Deprecation SLA (PRODUCT_BOUNDARY §29).

## Alternatives considered

- Keep dual kernels indefinitely — rejected (boundary clarity failure).
- Rename immediately — deferred; classification first, rename later via constitution bump.
