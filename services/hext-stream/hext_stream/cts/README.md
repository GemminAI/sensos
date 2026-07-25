# HEXT STREAM Conformance Test Suite (CTS) v1.0

Standards conformance suite for HEXT STREAM Runtime Reference Implementation v1.0.

**Not a benchmark.** Verifies ABI conformance only. Does not modify runtime architecture.

## Run

```bash
cd nvs-platform-runtime
PYTHONPATH=hext-stream python -m hext_stream.cts.run_cts
```

With live Docker runtime (Redis backend on port 8030):

```bash
docker compose -f hext-stream/docker-compose.yml up -d
PYTHONPATH=hext-stream python -m hext_stream.cts.run_cts
```

## Backends tested

| Backend | Mode |
|---------|------|
| `inprocess` | Direct ABI + FastAPI TestClient |
| `redis` | Direct ABI against Redis Streams |
| `http_redis` | HTTP client against docker runtime (optional) |

## Deliverables

Written to `hext_stream/cts/results/`:

- `CTS_Report.md`
- `metrics.csv`
- `latency.csv`
- `throughput.csv`
- `ordering.csv`
- `replay_validation.csv`
- `backend_comparison.csv`
- `history_validation.csv`
- `lawvere_contraction.csv`
- `diagram_compatibility.md`

All measurements are from live runtime execution. No synthetic or mocked metrics.

## Test coverage

CTS-01 through CTS-16, plus Trajectory Flow, Lawvere Contraction, and String Diagram compatibility extensions.

## Known ABI notes

- `/health` returns `status: ok` (not `healthy`); CTS records actual response.
- `version` and `uptime` fields are not yet exposed in `/health`; CTS measures client-side uptime.
