# Migration from nvs-platform-runtime

This document records what entered `GemminAI/sensos` and what stayed out.

## Migrated (production)

| Source | Destination |
|--------|-------------|
| `sensos/` | `services/observation-runtime/sensos/` |
| `runtime/` | `services/nvs-runtime/runtime/` |
| `semantic-annotator/` | `services/semantic-annotator/` |
| `hext-stream/` (no CTS result dumps) | `services/hext-stream/` |
| `hekb/` (projection face) | `integrations/hekb-projection/` |
| `hekb_mcp/` (no experiment reports) | `integrations/hekb-mcp/` |
| `sensos/abi/` | also published at `interfaces/nvs-kernel/abi/` |
| `proto/runtime.proto` | `interfaces/proto/runtime.proto` |
| `shared/runtime-ui/` | `packages/runtime-ui/` |
| `config/{auth,dak,runtime}.yaml` | `configs/` |
| Product helpers in `scripts/` | `scripts/` |
| Product tests | `tests/` |

## New packaging (no algorithm changes)

| Unit | Notes |
|------|-------|
| `services/gateway/` | Nginx edge reverse proxy |
| `services/dashboard/` | Operator shell release unit |

## Explicitly not migrated

| Source | Reason |
|--------|--------|
| `sensos-exp4000/` | Research experiment runtime |
| `docs/EXP-*`, experiment reports | Research Vault |
| `reports/`, `logs/` | Generated artifacts |
| `kernel/` | Legacy; superseded by Observation Runtime |
| `docker-compose.yml` (Phase37-C) | Deprecated |
| `nvs-kernel/` nested tree | Proprietary core stays external |
| `hekb-core/` nested tree | OSS HEKB stays external dependency |
| `hekb-runtime/`, `trajectory-engine/`, `exp6000`… | Platform libraries; not this product cut |
| `sensos-certification/` | Internal harness |

## Rules preserved

- No HEKB implementation vendoring
- No HEXT definition duplication
- NVS-Kernel source remains proprietary / external
- Algorithms unchanged during the move
