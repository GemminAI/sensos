# SensOS

SensOS is an observation-centered intelligence platform that transforms observations into actionable runtime decisions.

It is the production integration layer of the HEXT AI ecosystem: deployable services that connect observation, knowledge, and applications.

## Architecture

```text
Observation
      │
      ▼
Semantic Annotator
      │
      ▼
HEKB
      │
      ▼
NVS Runtime
      │
      ▼
NVS-Kernel API
      │
      ▼
Applications
```

Gateway is the public edge. Dashboard is the operator UI. Neither changes the data path above.

```text
HEXT defines.
HEKB stores.
SensOS operates.
NVS-Kernel decides.
```

## Components

| Component | Role |
|-----------|------|
| **Observation Runtime** | Ingests signals, runs observation modules, and schedules work before meaning is attached. |
| **Semantic Annotator** | Attaches HEXT-compatible meaning to observations. |
| **HEKB** | External Apache-2.0 knowledge store. SensOS calls it through a thin adapter; the implementation is not in this repository. |
| **NVS Runtime** | Application plane: agents, sessions, events, and MCP. |
| **Gateway** | Reverse proxy and single public entry for product services. |
| **Dashboard** | Operator console for health and platform status. |

## Getting Started

Requirements: Docker Engine 24+ and Compose v2.

1. Copy the development template and generate your own secrets:

```bash
cp .env.example .env
# Replace every CHANGE_ME value. Example:
#   openssl rand -base64 32
```

`.env.example` is a development template only. Never commit `.env`. Never use template values in production. Production secrets must come from a secret manager or the deployment environment—not from files in this repository.

2. Start the stack:

```bash
docker compose --env-file .env -f compose/docker-compose.yml up --build -d
# or
make up

curl -s http://localhost:8080/healthz
```

| Service | Local URL |
|---------|-----------|
| Gateway | http://localhost:8080 |
| Observation Runtime | http://localhost:8090 |
| Semantic Annotator | http://localhost:8011 |
| NVS Runtime | http://localhost:8020 |
| Dashboard | http://localhost:3000 |

## Ecosystem

**HEXT** defines.  
Semantic contracts and event shapes live in the HEXT specification and SDK.

**HEKB** stores.  
Knowledge objects and morphisms live in the HEKB repository (Apache-2.0).

**SensOS** operates.  
This repository deploys and integrates the runtimes that move data from observation to applications.

**NVS-Kernel** decides.  
The commercial kernel implements decision semantics behind a published API; its source is not here.

## Repository Boundaries

This repository owns:

- Observation Runtime
- Semantic Annotator
- NVS Runtime
- Gateway
- Dashboard
- Docker Compose, deployment configs, and Kubernetes manifests

This repository does not contain:

- HEXT specification or SDK
- HEKB implementation
- NVS-Kernel implementation
- Research artifacts

Adapters under `integrations/` call HEKB. Interfaces under `interfaces/` publish the NVS-Kernel ABI. Neither vendors upstream source.

## Documentation

| Document | Contents |
|----------|----------|
| [`docs/architecture/overview.md`](docs/architecture/overview.md) | Architecture and service communication |
| [`docs/spec/PRODUCT_BOUNDARY.md`](docs/spec/PRODUCT_BOUNDARY.md) | Product constitution and ownership rules |
| [`docs/deployment/compose.md`](docs/deployment/compose.md) | Compose bring-up |
| [`docs/operations/runbook.md`](docs/operations/runbook.md) | Operations |
| [`docs/api/README.md`](docs/api/README.md) | API index |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution rules |
| [`SECURITY.md`](SECURITY.md) | Vulnerability reporting |
| [`ROADMAP.md`](ROADMAP.md) | Release roadmap |

## License

Proprietary. Copyright © Gemmina Intelligence LLC. See [`LICENSE`](LICENSE).

HEKB and other OSS dependencies remain under their own licenses.

## Related Projects

- **HEXT** — Canonical object model and specification.
- **HEKB** — Apache 2.0 content-addressed knowledge substrate.
- **NVS-Kernel** — Commercial decision engine accessed through public APIs.

Learn more about the ecosystem at **[hextai.com](https://hextai.com)**.
