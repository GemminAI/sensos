# HEKB Runtime (Python)

Independent execution environment for the Knowledge Runtime. FastAPI +
pydantic v2, dependency-managed with `uv`.

Two `hekb-runtime` components now exist in this repository, deliberately
kept separate:

| | Language / Stack | Role |
|---|---|---|
| `hekb-runtime/` | C++20 / CMake / LMDB / cpp-httplib | EXP-7100 reference implementation |
| `hekb/` (this directory) | Python 3.12 / FastAPI / uv | Projection Runtime implementation (RFC-HEKB08 design input) |

Neither is modified by the other. Which one becomes the canonical HEKB
Runtime is a decision deferred to a later phase, once both have been
evaluated experimentally. This phase does not wire `hekb/` to EXP-7100 --
that integration is planned for a following phase.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker + Docker Compose (for container use)

## Local development

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8080
```

## Quality checks

```bash
uv run ruff check .
uv run mypy
uv run pytest
```

## Docker

```bash
docker compose up --build
curl http://localhost:8080/health
```

## Endpoints

- `GET /health`
- `GET /version`
- `GET /storage/profile` -- returns the active `StorageBackend`'s declarative `StorageProfile`

## Storage

`StorageBackend` is a `Protocol` (`app/storage/protocol.py`). The only
implementation in this phase is `InMemoryStorageBackend`
(`app/storage/in_memory.py`) -- non-persistent, process-local.

`ProjectionBackend` (`app/storage/projection.py`) is the physical
projection interface (design input: an RFC-HEKB08 draft manifesto pasted
into this phase's task, not yet reconciled with the vault's published
`RFC-HEKB08_v1.0.md`, which describes a different projection design). No
concrete `ProjectionBackend` implementation exists yet.

## Not implemented (TODO, out of scope for this phase)

- LMDB / ScyllaDB / PostgreSQL / Redis storage backends
- Authentication / Authorization
- Knowledge Graph traversal
- Vector Search
- Background Jobs
- Wiring to EXP-7100
