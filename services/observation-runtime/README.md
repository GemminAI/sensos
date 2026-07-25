# Observation Runtime

SensOS Observation Runtime (package: `sensos`).

Observes, schedules, and applies DAK (Trajectory Differential Safety) before
downstream meaning and knowledge stages.

## Run locally

```bash
uv sync --dev
uv run uvicorn sensos.api.app:create_app --factory --host 0.0.0.0 --port 8090
```

## Container

```bash
docker build -t sensos/observation-runtime:0.3.0 -f Dockerfile .
```

## Notes

- Algorithms are unchanged from the prior `sensos/` product package.
- NVS-Kernel ABI used by this service is also published at repo
  `interfaces/nvs-kernel/` for external consumers.
