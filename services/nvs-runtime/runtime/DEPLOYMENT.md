# MCP Runtime Server — Deployment Instructions

## Prerequisites

- Docker & Docker Compose
- NVS-Kernel running (included in compose)

## Quick Start

```bash
cd infrastructure/docker
docker compose up -d postgres redis nvs-kernel nvs-runtime
```

## Services

| Service | URL | Port |
|---------|-----|------|
| nvs-runtime REST | http://localhost:8020/api/v1 | 8020 |
| nvs-runtime health | http://localhost:8020/health | 8020 |
| nvs-kernel | http://localhost:8000 | 8000 |
| PostgreSQL | postgres:5432 | 5432 |
| Redis | redis:6379 | 6379 |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://nvs:nvs@postgres:5432/nvs_runtime` | PostgreSQL connection |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `NVS_KERNEL_URL` | `http://nvs-kernel:8000` | Kernel gateway target |

## Database Migration

Schema is applied automatically via `migrations/001_initial.sql` on first PostgreSQL start.

Manual apply:

```bash
psql $DATABASE_URL -f migrations/001_initial.sql
```

## MCP Server (stdio)

```bash
cd /path/to/nvs-platform
PYTHONPATH=. python -m runtime.mcp.server
```

## Local Development

```bash
cd runtime
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://nvs:nvs@localhost:5432/nvs_runtime
export REDIS_URL=redis://localhost:6379/0
export NVS_KERNEL_URL=http://localhost:8000
uvicorn runtime.main:app --reload --port 8020
```

## Tests

```bash
cd runtime
PYTHONPATH=.. .venv/bin/pytest tests/ --cov=runtime
```

## API Examples

```bash
# Register agent
curl -X POST http://localhost:8020/api/v1/agents \
  -H 'Content-Type: application/json' \
  -d '{"provider":"anthropic","model":"claude-sonnet-4","capabilities":["sep.excitation"]}'

# Create session
curl -X POST http://localhost:8020/api/v1/sessions \
  -H 'Content-Type: application/json' \
  -d '{"label":"demo"}'

# Emit SEP event
curl -X POST http://localhost:8020/api/v1/sessions/{session_id}/events \
  -H 'Content-Type: application/json' \
  -d '{
    "event_type":"sep.excitation",
    "agent_id":"{agent_id}",
    "source_provider":"anthropic",
    "payload":{
      "sep_version":"nvs.sep.event.v1",
      "event_id":"'$(uuidgen)'",
      "event_type":"excitation.step",
      "timestamp":"2026-06-14T12:00:00.000Z",
      "payload":{"amplitude":0.5,"basis":"35TAG"}
    }
  }'

# SSE stream
curl -N http://localhost:8020/api/v1/sessions/{session_id}/stream
```
