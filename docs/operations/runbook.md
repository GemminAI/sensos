# SensOS operations runbook

## Health checks

```bash
# Edge
curl -sf http://localhost:8080/healthz

# Direct (debug only)
curl -sf http://localhost:8090/health   # observation-runtime
curl -sf http://localhost:8011/health   # semantic-annotator
curl -sf http://localhost:8030/health   # hext-stream
curl -sf http://localhost:8040/health   # hekb-projection (mapped)
curl -sf http://localhost:8020/health   # nvs-runtime (profile runtime)
```

## Common failures

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Gateway 502 | Upstream not healthy | `docker compose -f compose/docker-compose.yml ps` |
| Annotator unhealthy | Missing LLM API keys (if required) | Check env; use mock backends for local |
| HEXT Stream down | Redis not ready | Wait for redis health; check `REDIS_URL` |
| HEKB projection restart loop | Volume / data dir perms | Inspect `hekb_data` volume |
| NVS Runtime auth errors | Weak/missing JWT secret | Set `NVS_JWT_SECRET` to a generated secret (≥32 bytes); never use `CHANGE_ME` |

## Logs

```bash
docker compose -f compose/docker-compose.yml logs -f gateway
docker compose -f compose/docker-compose.yml logs -f observation-runtime
docker compose -f compose/docker-compose.yml logs -f nvs-runtime
```

## Restart a single service

```bash
docker compose -f compose/docker-compose.yml up -d --no-deps --build semantic-annotator
```

## Boundary reminders

- Do not exec into containers to “patch” HEKB core — upgrade the external dependency
- Do not place experiment outputs under `logs/` into git
- Escalate security issues per `SECURITY.md`
