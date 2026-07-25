# docker/

Shared image helpers for SensOS.

Prefer service-local Dockerfiles:

- `services/observation-runtime/Dockerfile`
- `services/semantic-annotator/Dockerfile`
- `services/nvs-runtime/Dockerfile`
- `services/gateway/Dockerfile`
- `services/dashboard/Dockerfile`
- `services/hext-stream/Dockerfile`
- `integrations/hekb-projection/Dockerfile`

Add cross-cutting base images here only when multiple services share a hardened base.
