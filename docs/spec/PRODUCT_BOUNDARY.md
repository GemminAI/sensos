# PRODUCT_BOUNDARY

| Field | Value |
|-------|-------|
| Document | Product Constitution |
| Path | `docs/spec/PRODUCT_BOUNDARY.md` |
| Version | 2.0.0 |
| Status | Active |
| Scope | Entire repository `GemminAI/sensos` |
| Authority | Single Source of Truth for product boundary |

**All agents and developers MUST treat this document as the sole boundary definition for this repository.**

---

## 1. Mission

This repository is the **commercial SensOS product**.

It is an integration product built on the HEXT AI ecosystem.

It is **not**:

- a research vault
- an experiment archive
- an OSS framework substitute for HEKB / HEXT

| Concern | Location |
|---------|----------|
| Product code, adapters, interfaces, deploy, ops docs | This repository |
| Papers, RFC drafts, experiments, notebooks, metrics | Research Vault |

---

## 2. Canonical architecture

```text
Observation
    ↓
Semantic Annotator
    ↓
HEKB
    ↓
NVS Runtime
    ↓
Applications
```

| Layer | Location | Notes |
|-------|----------|-------|
| Observation Runtime | `services/observation-runtime/` | Product |
| Semantic Annotator | `services/semantic-annotator/` | Product |
| HEXT Stream | `services/hext-stream/` | Product (meaning plane) |
| HEKB | External OSS | Consumed via `integrations/hekb-projection/` |
| NVS Runtime | `services/nvs-runtime/` | Product |
| Gateway | `services/gateway/` | Product edge |
| Dashboard | `services/dashboard/` | Product UI release unit |
| NVS-Kernel | External proprietary | ABI only in `interfaces/nvs-kernel/` |

---

## 3. Boundary rules

### 3.1 HEKB

- HEKB is an **external OSS dependency**
- Do **not** copy HEKB implementation into this repository
- SensOS may ship only adapters / projection faces under `integrations/`

### 3.2 HEXT

- HEXT Specification and HEXT SDK remain upstream
- Do **not** duplicate HEXT definitions in product code
- Consume via Annotator / Stream services and published SDK packages

### 3.3 NVS-Kernel

- NVS-Kernel remains **proprietary** and outside this tree
- Keep interfaces clean under `interfaces/nvs-kernel/`
- Product services talk to the kernel through ABI / HTTP gateway clients

### 3.4 Research

Forbidden in this repository:

- experiment harnesses and dashboards
- benchmark archives
- report / figure dumps
- temporary validation notebooks

---

## 4. Allowed tree

```text
services/           Product containers
integrations/       SensOS-side adapters to OSS
interfaces/         Published ABI / protobuf
packages/           Shared libraries
compose/            Compose orchestration
docker/             Shared image helpers
deployment/         K8s / Helm skeletons
configs/            Product configuration
docs/               Architecture, deploy, ops, API
scripts/            Ops helpers
examples/           Minimal product examples
tests/              Product tests
.github/            CI
```

---

## 5. Container policy

One concern per container. Required product containers:

- `observation-runtime`
- `semantic-annotator`
- `nvs-runtime`
- `gateway`
- `dashboard`

Supporting product containers may include `hext-stream` and `hekb-projection`.

A single mega-container that collapses these boundaries is forbidden.

---

## 6. Document authority

```text
PRODUCT_BOUNDARY.md
        ↓
ADR
        ↓
Specification / Architecture
        ↓
API docs
        ↓
README
```

Conflicts resolve top-down in favor of this constitution.
