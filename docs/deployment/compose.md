# Compose deployment

Canonical local / staging orchestration lives in:

```bash
compose/docker-compose.yml
```

## Bring-up

```bash
# 1. Local secrets (required)
cp .env.example .env
# Replace every CHANGE_ME. Never commit .env.
# Production: inject secrets from a secret manager / deployment env instead.

# 2. Full product stack
docker compose --env-file .env -f compose/docker-compose.yml up --build -d

# Validate rendered config
docker compose --env-file .env -f compose/docker-compose.yml config

# Tear down
docker compose --env-file .env -f compose/docker-compose.yml down
```

Compose fails fast if `POSTGRES_PASSWORD` or `NVS_JWT_SECRET` are unset.
There are no default passwords or JWT secrets in the compose file.

## Default services

gateway, dashboard, observation-runtime, semantic-annotator, hext-stream,
hekb-projection, nvs-runtime, redis, postgres, mock-llm

## Image boundaries

Each product concern has its own Dockerfile under the service directory.
Shared helper Dockerfiles (if any) live in `docker/`.

Do not collapse services into a single mega-image.

## Configuration

Host-mounted product configs:

```text
configs/auth.yaml
configs/dak.yaml
configs/runtime.yaml
```

Secrets via `.env` (from `.env.example`) or a secret manager.  
`.env.example` values are non-functional placeholders. Never commit real secrets.

## Production note

Compose is the reference topology. Kubernetes / Helm skeletons under
`deployment/` mirror the same service split; promote images from the same
Dockerfiles.
