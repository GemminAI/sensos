# Kubernetes skeleton

Manifests here intentionally start minimal. Promote the same images built from
`services/*/Dockerfile` and keep one Deployment per product container.

Suggested workloads:

- `gateway`
- `dashboard`
- `observation-runtime`
- `semantic-annotator`
- `hext-stream`
- `hekb-projection`
- `nvs-runtime`
- `redis` / `postgres` (managed services preferred in production)

Add Ingress only to `gateway` in production topologies.
