# SensOS Roadmap

This roadmap tracks product delivery for the commercial SensOS platform.
Research tracks live in the Research Vault, not here.

## Now (v0.3 — Integration Platform)

- [x] Production repository layout (`GemminAI/sensos`)
- [x] Separated product services with Docker packaging
- [x] Compose orchestration for local / staging bring-up
- [x] Clean HEKB boundary (adapter only; no OSS core vendoring)
- [x] NVS-Kernel ABI published under `interfaces/`
- [ ] Unified SemVer across release units
- [ ] Hardened Gateway edge (authn/authz, rate limits)
- [ ] First-class Dashboard release unit

## Next (v0.4 — Operability)

- [ ] Kubernetes / Helm reference charts under `deployment/`
- [ ] Structured observability (metrics, traces, audit logs)
- [ ] Production configuration profiles (`configs/production`)
- [ ] Signed container images and SBOM generation
- [ ] Contract tests against HEKB / HEXT SDK releases

## Later (v1.0 — Commercial GA)

- [ ] Multi-tenant Gateway
- [ ] HA Observation Runtime
- [ ] Support matrix for HEKB + HEXT SDK LTS pairs
- [ ] Customer-facing operations runbooks
- [ ] SLA-backed release train

## Explicitly out of scope for this repository

- Research papers, RFC drafts, experiment notebooks
- Benchmark archives and metric dumps
- Vendoring HEKB / HEXT specification implementations
- NVS-Kernel proprietary source (ships separately)
