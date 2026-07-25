# Interfaces

Published contracts for SensOS integrations.

| Path | Purpose |
|------|---------|
| `nvs-kernel/abi/` | Proprietary NVS-Kernel ABI surface consumed by product services |
| `proto/runtime.proto` | Runtime protobuf IDL |

## Rules

- NVS-Kernel **implementation** does not live in this repository
- Prefer additive, versioned ABI changes
- Do not redefine HEXT or HEKB types here — depend on upstream packages
