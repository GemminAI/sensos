# SensOS API index

This index points to the HTTP surfaces of product services.
OpenAPI docs are served by each FastAPI service when running.

| Service | Base URL (local) | OpenAPI |
|---------|------------------|---------|
| Gateway | `http://localhost:8080` | Edge routes only (`/healthz`, proxies) |
| Observation Runtime | `http://localhost:8090` | `/docs` |
| Semantic Annotator | `http://localhost:8011` | `/docs` |
| HEXT Stream | `http://localhost:8030` | `/docs` |
| HEKB Projection | `http://localhost:8040` | `/docs` |
| NVS Runtime | `http://localhost:8020` | `/docs` |

## Contracts

| Contract | Path |
|----------|------|
| NVS-Kernel ABI | `interfaces/nvs-kernel/abi/` |
| Runtime protobuf | `interfaces/proto/runtime.proto` |

Upstream HEXT / HEKB API contracts remain in their respective OSS repositories.
