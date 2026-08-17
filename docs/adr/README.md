# Architecture Decision Records

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-0005](ADR-0005-production-repository-layout.md) | Production repository layout for GemminAI/sensos | Accepted |
| [ADR-0012](ADR-0012-deployment-migration-to-distributed-runtime.md) | Deployment Topology Migration to Distributed Runtime for Integrated Validation | Accepted |
| [ADR-0013](ADR-0013-hekb-canonical-backend-hekbd.md) | HEKB canonical backend is hekbd (C++), not hekb-api (Python) | Accepted |
| [ADR-0014](ADR-0014-gpt-oss-semantic-anchor.md) | GPT-OSS as a Semantic Anchor Provider (new capability, not an NVS-Kernel integration) | Accepted |

Note: ADR-0006–ADR-0011 do not exist in this repository. This gap is
unexplained and is not filled by this entry; if those decisions exist
elsewhere they should be reconciled into this index separately.

Older ADR files copied from `nvs-platform-runtime` (if present) are **historical
context** only. Path references in those documents may point at the prior
repository layout. For current boundaries, prefer:

1. `docs/spec/PRODUCT_BOUNDARY.md`
2. ADR-0005
3. `docs/architecture/overview.md`
