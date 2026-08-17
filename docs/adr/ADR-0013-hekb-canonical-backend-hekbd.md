# ADR-0013: HEKB canonical backend is hekbd (C++), not hekb-api (Python)

| Field | Value |
|-------|-------|
| Status | Accepted |
| Date | 2026-08-18 |
| Constitution | `docs/spec/PRODUCT_BOUNDARY.md` §"HEKB / HEXT / NVS-Kernel remain external dependencies" |
| Related | ADR-0003 (a different dual-backend question — see Scope below), `docs/audit/MCP_COMPLIANCE_AUDIT_20260818.md` |

## Scope (not to be confused with ADR-0003)

ADR-0003 decided between two **sensos-internal** packages descended from the
EXP5400 archive: `integrations/hekb-projection` (Python/FastAPI, a
self-admittedly unfinished storage-adapter skeleton — see
`docs/audit/EXP5400_ARCHIVE_HEKB_MCP_REUSE_AUDIT_20260817.md`) and the
excluded-from-migration `hekb-runtime/` (C++/EXP-7100). Neither of those is
what `runtime.gateway.hekb_client.HekbClient` actually talks to today.

This ADR is about a **different** pair, both inside the **external OSS
dependency `GemminAI/hekb`** (never vendored, per PRODUCT_BOUNDARY):

| Server | Stack | Port (default) | Confirmed by |
|---|---|---|---|
| `hekbd` | C++20, `cpp/server/http_api.cpp` | 8100 | `GemminAI/hekb/docs/API.md`; `hekb/python/hekb/client.py`'s own `DEFAULT_BASE_URL` |
| `hekb-api` | Python, `python/hekb/api.py` (FastAPI) | 8080 | `GemminAI/hekb/docs/hekb-api.md` |

`runtime.gateway.hekb_client.HekbClient` was, until this ADR, split across
both: `store()` (used by `request_capability()` and
`request_meaning_trajectory()`) targeted `hekb_url` (hekb-api, 8080);
`get_object`/`nearest`/`neighbours`/`geodesic`/`stats`/`relate` (added for
HEKB Read MCP, previous cycle) targeted a separate `hekb_query_url`
(hekbd, 8100) because hekb-api does not implement those routes at all.

## Context (Reality Audit — what was actually measured, not assumed)

1. **Functional coverage.** `hekb-api` implements only `GET /health`,
   `POST/GET /v1/objects`, `POST /v1/search`, and a stubbed
   `POST /v1/closure` (`docs/hekb-api.md`, and confirmed live in the prior
   turn's `hekb` audit). It has **no morphisms endpoint, no
   nearest/neighbours/geodesic query, no `/metrics`**. `hekbd` implements
   the full contract: everything `hekb-api` has, plus
   `POST /v1/morphisms`, `GET/DELETE /v1/morphisms/{id}`,
   `POST /v1/morphisms/compose`, `GET /v1/query/{nearest,neighbours,geodesic}`,
   and `GET /metrics`.
2. **Storage is not shared.** `hekb-api` persists to its own SQLite file
   (`SqliteObjectStore`, `python/hekb/api_storage.py`); `hekbd` persists to
   its own `FileStore`/LMDB. Writing an object to one server does not make
   it visible, queryable, or relatable through the other — they are two
   independent stores that happen to implement an overlapping subset of
   the same object schema.
3. **Write-response shapes differ**, discovered live while wiring
   `request_meaning_triangulation()` (previous cycle): `hekb-api`'s
   `POST /v1/objects` returns `{"object_id","hash","timestamp"}`; `hekbd`'s
   returns `{"id"}` only. A caller written against one shape gets a
   `KeyError` against the other — confirmed by an actual failing live test
   before this fix.
4. **The OSS project's own reference client defaults to hekbd.**
   `GemminAI/hekb/python/hekb/client.py`: `DEFAULT_BASE_URL =
   "http://127.0.0.1:8100"`. `hekb-api`'s own module docstring
   (`python/hekb/api.py`) describes itself as existing "alongside `hekbd`
   ... as the Python-native surface a Python-only deployment (no C++
   toolchain available) can run directly" — i.e. hekb-api positions
   *itself* as the fallback, not hekbd.
5. **The Observation-Centered Knowledge Loop requires one shared graph.**
   Evidence written for one capability (e.g. Port results) must be
   reachable by `neighbours()`/`geodesic()` from evidence written by
   another (e.g. Triangulation summaries DERIVES-linked to trajectories).
   That is only possible if every writer and every reader target the same
   server.

## Decision

**`hekbd` (port 8100) is the canonical HEKB backend for all
`runtime.gateway.hekb_client.HekbClient` traffic — reads, writes, and
relates alike.** The `hekb_query_url`/`hekb_url` split introduced in the
previous cycle is retired: there is one setting, `hekb_url`, defaulting to
`http://127.0.0.1:8100`.

`hekb-api` is not deleted or declared unsupported — it remains a real,
documented part of `GemminAI/hekb` for environments without a C++
toolchain — but SensOS Runtime does not target it by default, and no
Runtime code should assume its response shapes going forward. Pointing
`hekb_url` at an `hekb-api` instance instead is still possible via
configuration, but `HekbClient` no longer special-cases that server's
narrower contract or different response shape; a deployment that chooses
`hekb-api` accepts that `nearest`/`neighbours`/`geodesic`/`relate`/`stats`
will fail against it (a real 404, not silently degraded).

## Consequences

- `HekbClient.store()`'s return value is normalized to
  `{"object_id": <hekbd's id>, "hash": <hekbd's id>}` (content-addressed:
  the id *is* the hash, the same convention `hekb-api`'s own
  `ObjectCreateResponse` already used — `hash == object_id` in every
  example observed) — so `request_capability()`/`request_meaning_trajectory()`
  (both read `stored.get("object_id")` only) needed no logic changes,
  only a settings-default change.
- `request_meaning_triangulation()`'s `call_query()`/`store()` special
  case (added last cycle specifically because of this split) is removed;
  it now calls `store()` like the other two capability functions.
- Every capability's evidence — Port results, Trajectories, Triangulation
  summaries — now lands in the same graph, so `neighbours()`/`geodesic()`
  reads can genuinely traverse across capabilities, not just within one.
- Existing tests that constructed `Settings(hekb_url="http://hekb-test:8080")`
  as an arbitrary mock host string are unaffected (the mock never talks to
  a real port); tests that asserted the old hekb-api-shaped `store()`
  response are updated to hekbd's actual shape.

## Alternatives considered

- **Keep the dual-URL split, document it clearly.** Rejected: it does not
  solve the shared-graph requirement (finding 5 above) — two backends can
  never share a graph regardless of how clearly the split is documented.
- **Standardize on hekb-api instead.** Rejected: it cannot serve
  `nearest`/`neighbours`/`geodesic`/`relate`/`stats` at all — the entire
  HEKB Read MCP tranche and Triangulation's DERIVES lineage would be
  unimplementable against it.
- **Run both, sync data between them.** Rejected: no such sync mechanism
  exists in `GemminAI/hekb`, and building one would be exactly the kind of
  new HEKB API this cycle's instructions prohibit inventing.
