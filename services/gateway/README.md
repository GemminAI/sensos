# Gateway

Public edge for SensOS. Routes external traffic to product services.

This container is infrastructure packaging only — it does not reimplement
product algorithms. In-process kernel forwarding remains in
`services/nvs-runtime/runtime/gateway/`.

## Routes

| Path | Upstream |
|------|----------|
| `/healthz` | Gateway liveness |
| `/observation/` | Observation Runtime |
| `/annotator/` | Semantic Annotator |
| `/hext/` | HEXT Stream |
| `/hekb/` | HEKB Projection |
| `/runtime/` | NVS Runtime |
| `/` | Dashboard |
