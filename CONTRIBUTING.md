# Contributing to SensOS

SensOS is a commercial product repository. Contributions must preserve product boundaries.

## Before you change code

1. Read [`docs/spec/PRODUCT_BOUNDARY.md`](docs/spec/PRODUCT_BOUNDARY.md)
2. Confirm the change belongs in **product**, not the Research Vault
3. Prefer the smallest PR that ships one concern

## Allowed changes

- Product services under `services/`
- SensOS-side adapters under `integrations/`
- Published interfaces under `interfaces/`
- Compose, deployment, configs, docs, CI

## Forbidden

- Vendoring HEKB / HEXT SDK / specification sources
- Adding research notebooks, experiment reports, benchmarks, or metric dumps
- Copying proprietary NVS-Kernel implementation into this tree
- One mega-container that collapses service boundaries

## Workflow

1. Branch from `main` (`feat/…`, `fix/…`, `docs/…`)
2. Keep algorithms unchanged unless the PR is explicitly an algorithm change
3. Update docs when boundaries or deploy topology change
4. Ensure `docker compose -f compose/docker-compose.yml config` succeeds
5. Open a PR with summary + test plan

## Local checks

```bash
# Compose validity
docker compose -f compose/docker-compose.yml config >/dev/null

# Observation Runtime unit tests (if Python env available)
cd services/observation-runtime && uv sync --dev && uv run pytest ../../tests -q
```

## Commit messages

Prefer concise, intent-focused messages:

- `docs: clarify HEKB boundary in README`
- `chore: split gateway edge container`
- `fix: correct annotator health probe path`

Do not commit secrets, `.env` files, or local venv/cache directories.
