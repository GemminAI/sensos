# ADR-0012: Deployment Topology Migration to Distributed Runtime for Integrated Validation

|Field|Value|
|---|---|
|Document|Architecture Decision Record|
|Path|`docs/adr/ADR-0012-deployment-migration-to-distributed-runtime.md`|
|Version|1.0.0|
|Status|**Accepted**|
|Date|2026-08-06|
|Authority|Architecture Owner · Release Manager|
|Supersedes|N/A|
|Related Specs|`PRODUCT_BOUNDARY.md` v2.0.0, `GIT_GOVERNANCE.md` v1.0.0, `EXP-Ubuntu010D/011`|

## 1. Context & Motivation

AI agents (e.g., Claude Code, Cursor) executing integration validation protocols (`EXP-Ubuntu010D` through `EXP-Ubuntu012`) encountered execution halts when attempting to migrate local Docker Compose network bindings (`http://nvs-kernel:8100`) to distributed external endpoints (GCP Node: `34.61.86.172`, Mac HEKB Node).

The agents halted due to strict compliance with `PRODUCT_BOUNDARY.md` §3.3, which states that NVS-Kernel is "reachable only from `nvs-runtime` over the internal docker network."

Without explicit architectural authorization distinguishing **Repository Boundary Rules** from **Deployment Network Topologies**, autonomous agents correctly prioritized constitutional safety over test execution.

## 2. Decision & Architectural Separation

To resolve this conflict while preserving the strict authority of `PRODUCT_BOUNDARY.md` v2.0.0, the Architecture Owner hereby establishes the following canonical separation:

### 2.1 Repository Boundary vs. Deployment Layer Decoupling

1. **Repository Boundary Invariance (`PRODUCT_BOUNDARY.md` = Single Source of Truth):**
    
    - The logical service boundaries, module responsibilities, ABI contracts (`interfaces/nvs-kernel/`), and zero-leakage rules defined in `PRODUCT_BOUNDARY.md` remain **100% immutable**.
        
    - No code alterations breaking the `KernelGateway` isolation pattern or introducing direct cross-component dependencies are permitted.
        
2. **Deployment Topology Independence (Deployment Layer):**
    
    - Environment variables (`.env`, `SENSOS_ENV`), Docker Compose profiles (`docker-compose.override.yml`), network routing parameters, and external IP endpoint bindings belong exclusively to the **Deployment Architecture Layer**.
        
    - Configuring `nvs-runtime` to communicate with remote NVS/CLE endpoints (e.g., GCP `34.61.86.172:8100/8000`) or remote HEKB endpoints via HTTP/WAN profiles does **NOT** violate the Repository Boundary of `PRODUCT_BOUNDARY.md`.
        

### 2.2 Direct Directives for Autonomous Execution Agents

- **Directive A1:** Autonomous agents (Claude Code, Cursor, CI Runners) are explicitly authorized and directed to execute Deployment Layer migrations (`EXP-Ubuntu010D`) including updating `.env`, override compose manifests, and network profiles (`SENSOS_ENV=wan` / `SENSOS_ENV=gcp`).
    
- **Directive A2:** Agents MUST NOT halt due to `PRODUCT_BOUNDARY.md` §3.3 when adjusting deployment configurations, provided the application logic and gateway abstractions remain untouched.
    
- **Directive A3:** In case of further deployment ambiguity, agents MUST apply the **Principle of Minimal Deployment Modification** and continue execution through completion.
    

## 3. Consequences & Compliance

### Positive Consequences

- Unblocks autonomous agents to complete `EXP-Ubuntu010D` and `EXP-Ubuntu011` without human loop-interruption.
    
- Establishes a formal governance trail conforming to `GIT_GOVERNANCE.md` §4 and `PRODUCT_BOUNDARY.md` §6.
    
- Maintains strict repository boundary safety while granting full operational flexibility at the infrastructure deployment level.
    

### Negative / Neutral Consequences

- Requires deployment manifests (`compose/docker-compose.override.yml`) to be maintained alongside local compose configurations.
    

## 4. Status Alignment in Governance Hierarchy

```
PRODUCT_BOUNDARY.md (v2.0.0 — Unchanged Higher Authority)
        ↓
ADR-0012 (Accepted — Explicit Deployment / Boundary Decoupling)
        ↓
EXP-Ubuntu010D / EXP-Ubuntu011 / EXP-Ubuntu012 Specifications
```