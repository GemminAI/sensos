# Compose deployment

Canonical local / staging orchestration lives in:

```bash
compose/docker-compose.yml
```

## Bring-up

```bash
# Full product stack
docker compose -f compose/docker-compose.yml up --build -d

# Validate rendered config
docker compose -f compose/docker-compose.yml config

# Tear down
docker compose -f compose/docker-compose.yml down
```

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

Secrets via environment variables (see `.env.example`). Never commit real secrets.

## Production note

Compose is the reference topology. Kubernetes / Helm skeletons under
`deployment/` mirror the same service split; promote images from the same
Dockerfiles.
