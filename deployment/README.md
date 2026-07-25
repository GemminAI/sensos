# Deployment

Reference deployment assets for SensOS.

| Path | Purpose |
|------|---------|
| `kubernetes/` | Manifest skeletons mirroring Compose topology |
| `helm/` | Chart workspace (forthcoming) |

Compose remains the fastest local reference:

```bash
docker compose -f compose/docker-compose.yml up --build -d
```

Production should preserve the same service split (Gateway edge, separate
Observation / Annotator / Runtime / Dashboard containers).
