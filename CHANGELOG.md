# Changelog

All notable changes to the SensOS product repository are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Security

- Reject template JWT secrets (`CHANGE_ME`, etc.) at NVS Runtime startup with a fatal error
- Require Compose secrets via `.env` (no published default passwords)
- Add Gitleaks and CodeQL workflows; document Secret Scanning / Push Protection intent
- Harden `.gitignore` for env files, keystores, and cloud credential filenames

### Added

- Initial production repository layout for `GemminAI/sensos`
- Product services under `services/` (observation-runtime, semantic-annotator, nvs-runtime, gateway, dashboard, hext-stream)
- HEKB adapters under `integrations/` (projection + MCP tools) without vendoring HEKB core
- Published NVS-Kernel ABI / protobuf under `interfaces/`
- Canonical Compose stack in `compose/docker-compose.yml`
- Deployment skeletons under `deployment/`
- Product constitution `docs/spec/PRODUCT_BOUNDARY.md` v2.0.0
- CI skeleton for boundary checks, compose validation, and image builds

### Changed

- Migrated production components from `nvs-platform-runtime` into an integration-oriented tree
- Separated Gateway edge and Dashboard into dedicated containers

### Removed (not migrated)

- Research experiment runtimes and dashboards
- Benchmark / report / metric archives
- Legacy Phase37-C compose and kernel package
- Nested HEKB core / NVS-Kernel source trees (remain external)

## [0.3.0] — Observation Runtime baseline

- SensOS Observation Runtime package `sensos-kernel` 0.3.0 (algorithms unchanged)
