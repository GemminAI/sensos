# SensOS Runtime v2.0 — Cross-Repository Architecture Audit

**Document ID**: SENSOS-RTV2-XAUDIT-001
**Status**: Architecture Entry Point for v2.0 — Gap Audit Only (no implementation performed)
**Audit date**: 2026-08-15
**Auditor role**: Chief Systems Architect / Evidence Auditor
**Method**: Source code inspection, git history, config/docker inspection, cross-repo grep, primary validation documents. No live network probes were performed (no wire traces captured in this pass — see §23).
**Governing rule**: SPEC ≠ CODE ≠ CONFIG ≠ LIVE ≠ WIRE. A claim is promoted only as far as its weakest link in that chain.

Status vocabulary used throughout: **VERIFIED** / **PROVISIONAL** / **UNVERIFIED** / **NOT_CONNECTED** / **NOT_IMPLEMENTED** / **CONTRADICTED** / **BLOCKED** / **NOT_EVALUABLE**.

---

## 1. Executive Summary

The core suspicion that motivated this audit is **confirmed**: the production SensOS Runtime (repo `sensos`, `services/nvs-runtime`) implements

```
Observation → NVS-Kernel (/observe) → CLE (/lift) → HEKB (/v1/objects)
```

— i.e. **NVS-first**, with CLE receiving NVS's already-computed geometric output (a 65-dim position vector plus Betti numbers / Euler characteristic), not raw narrative text. This is confirmed independently by the primary source (`SensOS_Runtime_v1_Integrated_Validation_Report.pdf`, commit `ce423a5`) and by direct code inspection of `gateway/kernel_gateway.py`, `gateway/cle_client.py`, `services/forward_worker.py`. CLE's `/ground` endpoint (real 5W1H grounding, accepts raw text) exists, is routed, and is tested — in a **different** repository (`categorical-lift-engine`) — but the production runtime never calls it. The intended v2.0 pipeline (`CLE grounding → NVS → GPT-OSS → 38 Ports → DAK → HEKB`) is a **Candidate Architecture**, not yet built. Most of its individual pieces exist somewhere in the 13-repository GemminAI workspace, in isolation from each other; almost none of the inter-component edges the v2.0 spec requires are wired.

Two other findings materially change the shape of the problem beyond what any single prior document captured:

1. **Name collisions are a first-order risk.** Two unrelated "CLE" repos, two unrelated "HEKB" implementations (one of which — "sensos-hekb" — is referenced only in validation documents and has no local clone in this workspace), and two unrelated "nvs-runtime" projects (one inside `sensos`, one top-level) all share names but not code. Any v2.0 spec that references these names without a repo+commit pin is unverifiable by construction.
2. **The 38-Port capability is real and already lives in `nvs-kernel`** (not a repo previously known to be central to this problem) — `GET /ports` and the L0–L7 pipeline are implemented there, with `cognitive-port-selector` as a downstream, not-yet-wired consumer. Meanwhile GPT-OSS integration was **not located in any of the 13 audited repositories** — its location is unconfirmed, not merely unwired.

Full detail, per-edge status, and evidence citations follow in §§6–19.

---

## 2. Repositories Audited

| # | Repository | Path | Language / Stack | Role (as verified) |
|---|---|---|---|---|
| 1 | sensos | `/Users/tomonam3/GemminAI/sensos` | Python | Primary Runtime orchestrator |
| 2 | categorical-lift-engine | `/Users/tomonam3/GemminAI/categorical-lift-engine` | Python / FastAPI | "CLE" — semantic grounding + lift service |
| 3 | meaning-mapper | `/Users/tomonam3/GemminAI/meaning-mapper` | Python | Geometric observation-measurement library |
| 4 | hekb | `/Users/tomonam3/GemminAI/hekb` | Python + C++ | Content-addressed knowledge store ("HEKB", one of two) |
| 5 | nvs-mcp | `/Users/tomonam3/GemminAI/nvs-mcp` | Python | MCP server bridging agents to NVS/HEKB/Observation-Runtime |
| 6 | sensos-cle | `/Users/tomonam3/GemminAI/sensos-cle` | C++23 | "CLE" — calibration-only runtime (CLE-SPEC-01), unrelated to #2 |
| 7 | nvs-kernel | `/Users/tomonam3/GemminAI/nvs-kernel` | Python / FastAPI | The actual deployed NVS-Kernel physics engine; owns the 38-Port registry |
| 8 | cognitive-port-selector | `/Users/tomonam3/GemminAI/cognitive-port-selector` | Python / FastAPI | Downstream selector/ranker over nvs-kernel's 38 ports |
| 9 | hext | `/Users/tomonam3/GemminAI/hext` | Spec only (XSD) | HEXT standard definition; no runtime code |
| 10 | semantic-annotator-core | `/Users/tomonam3/GemminAI/semantic-annotator-core` | Python / FastAPI | Reference implementation, HEXT Observation normalization |
| 11 | meaning-space-runtime (MSR) | `/Users/tomonam3/GemminAI/meaning-space-runtime` | Python (library) | Meaning-physics middle layer (Protocol-coupled, not import-coupled) |
| 12 | nvs-runtime (top-level) | `/Users/tomonam3/GemminAI/nvs-runtime` | Python | Unrelated project; confirmed NOT the same code as `sensos/services/nvs-runtime` |
| 13 | sensos-docs | `/Users/tomonam3/GemminAI/sensos-docs` | Astro (docs site) | Canonical RFC/spec repository (SSOT), documents DAK spec (RFC-NVS-0206) |

Reference documents read (treated as prior claims, not ground truth, per §0 of the audit brief):
`SensOS_Runtime_v1_Integrated_Validation_Report.pdf`, `CLE-SPEC-01_Integrated_Validation_Report.md`, `CLE-HEKB-SPEC-01_Integrated_Validation_Report.md`, `HEKB-SPEC-01_Integrated_Validation_Report.md`, `03-semantic-abi-compatibility.md` (SIR-COMPAT-03), `DEPLOYMENT.md`, plus vault documents `SensOS Runtime v2.0 Integration Contract.md` (SPEC-SENSOS-RTV2-001), `Architecture Gap Audit.md` (SPEC-SENSOS-RTV2-GAP-001, dated 2026-08-14), `SPEC-SENSOS-RTV2-JSON-002.md`, `Categorical Architecture Specification.md`, `CLAUDE.md` (vault system directives).

Not locally present, referenced only in documents: **`sensos-hekb`** and **`sensos-cle-hekb`** (the calibration-first HEKB-SPEC-01 / joint-runtime repos described in the validation reports run on a different host, `/home/parallels/...`). These are **NOT_EVALUABLE** by this audit — no local clone exists in `/Users/tomonam3/GemminAI/`.

---

## 3. Repository Identity Matrix

| Name collision | Repo A | Repo B | Distinguishing evidence |
|---|---|---|---|
| **"CLE"** | `categorical-lift-engine` — Python/FastAPI, HTTP service, 5W1H grounding, hash-embeddings, deployed to GCP | `sensos-cle` — C++23, offline CTest calibration suite, HEXT = numeric FP64 tensor, explicitly "must not own" Meaning Space Runtime / HEKB / NVS-Kernel / semantic grounding | No shared code, no shared transport (one is HTTP, one has "No sockets/HTTP/gRPC/MCP" stated in its own ABI docs), no cross-references either direction |
| **"HEKB"** | `hekb` (this workspace) — content-addressed (BLAKE2b-256), Python (port 8080) + C++ (`hekbd`, port 8100) | `sensos-hekb` (referenced only in validation docs; **not locally present**) — calibration-first, HEKB-SPEC-01, explicitly excludes production vector/graph stores | `hekb`'s own docs (`docs/hekb-api.md:79`) state a *different, non-interoperable* HEKB implementation exists elsewhere in the org — self-disclosed, not inferred |
| **"nvs-runtime"** | `sensos/services/nvs-runtime` — Redis-backed ForwardWorker/KernelGateway/CLEClient/HekbClient forwarding pipeline | top-level `nvs-runtime` repo — generic provider-agnostic capability-graph runtime (Local/HTTP/gRPC/MCP/Kernel/HEKB providers), `Planner`/`Session Manager`/`Governance` | Zero shared class/module names (`ForwardWorker`, `KernelGateway`, `CLEClient`, `HekbClient`, `EventService`, `RedisService` absent from top-level repo); not a symlink, submodule, or subtree |

Single-identity components (no collision found): `meaning-mapper`, `nvs-mcp`, `nvs-kernel`, `cognitive-port-selector`, `hext`, `semantic-annotator-core`, `meaning-space-runtime`, `sensos-docs`.

---

## 4. Actual Dataflow (VERIFIED, production `sensos` repo, HEAD `52007a1`, 11 total commits)

```
POST /sessions/{id}/events                              [api/routes.py:82-84]
        │
        ▼
EventService.ingest()                                     [services/event_service.py:66-68]
        │  unconditional enqueue — no synchronous RPC
        ▼
Redis Outbox  (runtime:forward:queue)
        │
        ▼
ForwardWorker.drain_once()                                [services/forward_worker.py:83-149]
        │
        ▼
KernelGateway.observe_batch()  ──POST /observe──►  NVS-Kernel (nvs-kernel repo, GCP :8100)
        │  response.geometry.position (65-dim vector, betti_0/1/2, euler_characteristic)
        ▼  [gateway/kernel_gateway.py:107-133]
ForwardWorker._propagate_semantic_mapping()  (best-effort, non-blocking; runs only AFTER NVS commit)
        │
        ▼
CLEClient.lift(position)  ──POST /lift──►  CLE (categorical-lift-engine repo, GCP :8000)
        │  [gateway/cle_client.py:48-61] — position is wrapped as ConceptInput; NO raw text ever sent
        ▼
build_hekb_object(lift_result)  (field rename / type-coercion only — no new schema)
        │
        ▼
HekbClient.store()  ──POST /v1/objects──►  HEKB (hekb repo, Mac :8080)   kind=OBSERVATION
```

Construction order (git): NVS wiring (`57cf4f2`, "route KernelGateway through canonical /observe") landed **before** CLE/HEKB wiring (`ce423a5`, "wire Semantic Mapping from NVS to CLE and HEKB"). The architecture was built NVS-first as a matter of historical fact, not merely as a runtime call order — confirming the exact confusion the audit brief anticipated (§2 of the brief).

CLE/HEKB failures are caught and logged only; they never roll back or block the already-committed NVS forward (`forward_worker.py:171-181`).

A **second, disconnected** pipeline exists in the same `sensos` repo: `services/observation-runtime` (port 8090) runs its own LLM inference cycle (`KernelExecutive.run_cycle_structured`) with a real DAK instance. Zero cross-references exist between `services/nvs-runtime` (port 8020) and `services/observation-runtime` (port 8090) in either direction — confirmed by bidirectional grep. These are two silos inside one repository, not one integrated runtime.

---

## 5. Candidate V2 Dataflow (UNVERIFIED — specification only, per SPEC-SENSOS-RTV2-001 / vault Integration Contract)

```
Raw Narrative Stream
        │
        ▼
CLE Engine  (/ground: 5W1H + dense vector)
        │
        ▼
NVS-Kernel  (Geometry / Curvature κ(t))
        │
        ▼
GPT-OSS Engine  (Hidden State Ensemble S(t))
        │
        ▼
38-Port Matrix  (11 stateless + 27 session-scoped; Observation/Attribution/Intervention/Control)
        │
        ▼
DAK Controller  (Semantic Re-Melting / Quenching)
        │
        ▼
HEKB Persistence  (Canonical Memory, append-only trace)
```

This diagram is **not to be treated as fact** — see §17/§18 for which single edges of it are actually wired today (nearly none, in this exact sequence).

---

## 6. CLE Grounding Audit

**Repo: `categorical-lift-engine`.**

- Identity: Python/FastAPI service. README frames it as SensOS's "optional Knowledge Generation extension" converting an already-`StabilizedTrajectory` (MSR output) into `Concept`/`Category`/`KnowledgeDelta` via a 9-stage pipeline. **VERIFIED.**
- `/lift` accepts only numeric input: `ConceptInput{states: list[MeaningStatePoint{theta: list[float]}]}` (`src/cle/api/models.py:22-40`) — cannot accept raw text. **VERIFIED.**
- `/ground` accepts raw text: `GroundRequest{prompt: str, goal: str, ...}` (`api/models.py:160-168`), is registered on the FastAPI router (`@router.post("/ground")` at `api/router.py:161`, included via `app.include_router(router)` at `api/app.py:33`), and is exercised by 5 passing tests via `TestClient(app)`. **VERIFIED — this directly contradicts the vault "Architecture Gap Audit" claim that `/ground` is unrouted (HTTP 404).** Reconciliation: the audit's 404 observation and this repo's own in-repo live-verification report both **predate** `/ground`'s existence in source (commit `b8f6781`, added 2026-08-12) — see §16 for the timeline. Whether the live GCP deployment has been updated since is **UNVERIFIED** (no fresh live probe performed in this audit).
- 5W1H grounding is **deterministic and rules-based** — regex time/location extraction, `what`=goal, `why`=prompt, `how`=first sentence (`src/cle/grounding/five_w1h.py`). Not an LLM call; no LLM SDK imports anywhere in `src/cle`. **VERIFIED.**
- "Dense vector representation" is a **disclosed SHA-256 character-trigram hash-embedding** (`src/cle/grounding/embedding.py:26-33`, explicit docstring: "No learned weights, no external model call... not a semantic embedding model"), default dimension 8. **VERIFIED — this is not a real embedding model; do not treat `dense_projection_vector` in the v2 spec examples as an existing capability.**
- CLE → NVS edge: **NOT_IMPLEMENTED as an HTTP call.** No `httpx`/`requests` import anywhere in `src/cle`. NVS is referenced only as a `typing.Protocol` recovery port (`src/cle/ports/recovery.py`) that an external composition root may structurally satisfy via dependency injection — CLE never dials out to NVS itself. **VERIFIED (NOT_CONNECTED as network edge).**
- Deployment provenance: version/route match between this repo and the live GCP `34.61.86.172:8000` was observed in an in-repo report (pre-grounding), but container/process identity was explicitly left "UNRESOLVED" by that report's own authors. **UNVERIFIED / NOT_EVALUABLE.**

---

## 7. Meaning Mapper Audit

**Repo: `meaning-mapper`.**

- What it does: a pure, deterministic 8-stage **geometric measurement pipeline** — `map_observation(HEXTObservation) -> MeasurementResult`, producing `theta` (position), `sigma` (covariance), `density`. **This is not a 5W1H/TAG system.** **VERIFIED.**
- No HTTP API, no CLI (grep for FastAPI/Flask/argparse/click/typer/`console_scripts`: zero hits). It is a library only. **VERIFIED.**
- 5W1H exists in this repo **only** as wire-format structs (`FiveW1H`, `FiveW1HField`) for optional overrides sent outbound to CLE's `/ground` — added 2026-08-12 as a thin `httpx` client (`src/meaning_mapper/cle/client.py`), never as something Meaning Mapper itself derives. **VERIFIED.**
- TAG generation (`35TAG`, `24TAG`, `tag_generator`): **NOT_IMPLEMENTED** — zero matches anywhere, current or `legacy/`.
- `legacy/` is an "Annotation Service" (RFC-SA001–SA005), **not a TAG Generator** — this premise from prior assumptions is **CONTRADICTED**.
- Git history shows a Categorical Lift implementation was briefly embedded directly in this repo for **under 12 hours on one day** (2026-08-04, commit `40173b7`) then reverted the same day (`6814f83`, message: "Categorical Lift is Pro-tier knowledge generation (CLE), not OSS-tier measurement"). CLE was never merged into meaning-mapper as a lasting state. **VERIFIED.**
- Production consumer search across the entire 13-repo workspace: **zero repos import `meaning_mapper`**; the only references are documentation/URL mentions (`categorical-lift-engine/pyproject.toml`, `meaning-space-runtime/NOTICE`). **meaning-mapper is architecturally orphaned — a fully tested library with no verified caller.**

---

## 8. NVS-Kernel Audit

**Repo: `nvs-kernel`.**

- This is **the actual deployed NVS-Kernel physics engine** referenced throughout the v1.0 validation report (GCP `34.61.86.172:8100`). **VERIFIED** — matched by name, port, and capability: `POST /observe` (`api/routers/pipeline.py:70`), `GET /ports` (`api/routers/ports.py:39,53` — "Discover the 38-Core Observable Port Layer (P01_Port..P38_Port)"), plus `field/curvature.py`, `geometry/engine.py`, `manifold/hypersphere.py`, `hekb/graph.py` (geodesic queries).
- **The 38-Port capability's canonical source lives in `nvs-kernel`**, not in `cognitive-port-selector` (§10) — `ports/registry.py` implements the 38-Core registry directly.
- README states "It decides; it never executes" — consistent with the v1.0 report's finding that NVS produces observation/geometry but does not itself intervene.
- L0–L7 internal pipeline (per the vault gap-audit's live-probe claim of L0/L7 = `NOT_IMPLEMENTED`) was **not independently re-verified via a fresh live probe** in this audit — the module structure (`control/` = "L0–L7 tiers, gains, interlock, checkpoints") is present in source, consistent with but not proof against the prior claim. **PROVISIONAL.**
- GPT-OSS references: **not checked by name in this repo** during the audit (a gap in this audit's own coverage — flagged in §22).

---

## 9. NVS-MCP Audit

**Repo: `nvs-mcp`.**

- Implements a real MCP server (official `mcp` SDK) exposing 19 base L-Port tools (`discover_ports`, `invoke_port`, `plan_pipeline`, etc.) plus 8 RFC-MCP-001 "semantic" tools (`hekb.query`, `hekb.causal_graph`, `cal.negotiate`, `runtime.execute`, `hext.observe`, etc.) and 5 MCP resources. **VERIFIED**, full tool list enumerated by the sub-audit.
- Connects to NVS-Kernel via a real `httpx.AsyncClient` (`adapters/kernel_adapter.py`, `NVS_KERNEL_URL` env, default `127.0.0.1:8000`) — but **silently falls back** to a `{"status": "DEFERRED"}` response on any connection failure, never raising. **VERIFIED (real client, soft-fail behavior).**
- Connects to HEKB via a 3-tier fallback: real HTTP client → in-process package → pure in-memory dict (`offline_blob`) — whichever mode is active self-reports via a `"note"` field. **VERIFIED**, live-vs-offline status is environment-dependent and **NOT_EVALUABLE** statically.
- **Zero** connection to CLE (either repo) or GPT-OSS anywhere in source. **NOT_IMPLEMENTED.**
- No Semantic ABI / SIR envelope fields (`semantic_abi_version`, `sir_version`, `stable_id`, etc.) present anywhere. "Semantic" in this repo means the RFC-MCP-001 tool *namespace*, not a versioned payload envelope. **NOT_IMPLEMENTED.**
- `docker-compose.yml` confirms HEKB/NVS-Kernel/Observation-Runtime are expected as **separate, externally-run processes** this repo never bundles — consistent with its own docs ("Never in this repo: HEXT core, HEKB store engine, Kernel geometry").
- Cross-check with `sensos`: **`sensos` does not call `nvs-mcp`** at all (confirmed zero imports/references) — `sensos` instead runs its own, separate outbound MCP server (`services/nvs-runtime/runtime/mcp/server.py`, tool names `nvs_register_agent`, `nvs_create_session`, etc.). `nvs-mcp` and `sensos`'s own MCP server are two independent, non-overlapping MCP surfaces. **CONTRADICTED** (relative to an assumption that `sensos` might consume `nvs-mcp`).

---

## 10. GPT-OSS Audit

**No repository in this 13-repo audit contains a working GPT-OSS integration.**

- `sensos`: zero code hits for `gpt-oss`/`gptoss`/`gpt_oss`; only doc mentions (`CLAUDE.md`, draft V2 spec), both labeling the `NVS-Kernel → GPT-OSS` edge **UNVERIFIED** ("No session/state binding found"). The prior gap-audit's claimed "`sensos_cle_gptoss_*` isolated MLX scripts" were **not found in the `sensos` repo at all** — their actual location is unconfirmed by this audit; they may live in a repo/path outside the 13 audited here, or under a name pattern not grepped. **BLOCKED — location unconfirmed.**
- `nvs-mcp`: providers present are Claude, Gemini, generic OpenAI-compatible, Local heuristic, and Mock — **no gpt-oss-branded provider**. **NOT_IMPLEMENTED.**
- `nvs-kernel`: not checked by name for GPT-OSS in this pass (audit gap, see §22).
- `sensos/services/observation-runtime` (the DAK-consuming service) uses env vars `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `LOCAL_LLM_BASE_URL` — `LOCAL_LLM_BASE_URL` is a plausible candidate for a locally-hosted GPT-OSS endpoint, but this was **not confirmed** to actually point at GPT-OSS specifically. **UNVERIFIED.**

**Separation maintained per audit brief §9:** "GPT-OSS exists" (true, per external prior claims, not independently confirmed to be running by this audit) is not the same as "NVS-Kernel or any runtime observes GPT-OSS's internal state" (**NOT_CONNECTED**, no code found anywhere).

---

## 11. 38-Port Audit

- Canonical implementation: **`nvs-kernel`** (`ports/registry.py`, `GET /ports`). **VERIFIED** as existing and enumerable (P01–P38).
- `cognitive-port-selector`: a **downstream consumer**, not the origin. Sits `LLM → CPS → NVS-Kernel 38 Core/Port → CPS → LLM`, explicitly "never imports `nvs_kernel`" (structural/HTTP boundary). Consumes a **static 38-row CSV + 38-entry JSON snapshot** (`EXP_NVS_0001_38_PORT_Behavior_Matrix.csv`, `exp_nvs_0001_behavior_footprint.json`), hard-validated to exactly 38 rows at load time. Its own `DISCREPANCY_REPORT.md` reportedly documents disagreements between these two data sources — **not independently re-verified in this audit (NOT_EVALUABLE)**, but if accurate, means the "38 Ports" source of truth is not internally consistent even within already-existing implementations.
- Prior gap-audit's claim that the `sensos` production runtime contains **zero lines of code invoking any 38-Port API** was **independently reconfirmed**: `grep -rn "port_dispatcher|38.port|/ports/|port_id"` across all `.py` in `sensos` returns zero hits outside documentation. **VERIFIED.**
- Whether ports carry intervention/control fields (vs. pure observation, as the prior gap-audit's wire-trace grep claimed) was **not re-verified via a fresh live/wire probe** in this pass — carried forward as **PROVISIONAL** from the prior document, not independently reproduced.

---

## 12. DAK Audit

- Prior claim's file path (`sensos/kernels/dak/safety_kernel.py`) is **CONTRADICTED — wrong path.** Real location: `services/observation-runtime/sensos/dak/kernel.py`, class `TrajectoryDifferentialSafetyKernel`.
- Computation: linear risk score `risk_rh = 0.5·ΔT + 0.3·κ + 0.2·H` from three trajectory metrics, mapped to a `DAKDecision` enum (CONTINUE/CORRECT/RETRIEVE/ESCALATE/ABORT) via three thresholds. Matches the "simple 3-metric linear risk score" characterization. **VERIFIED.**
- Prior claim of "**no downstream caller**" is **partially CONTRADICTED**: `KernelExecutive.run_cycle_structured` (`observation-runtime/sensos/kernel/executive.py`) does instantiate DAK and does branch on its output with real control flow (CORRECT rewrites the prompt; ESCALATE/ABORT terminate the cycle), reachable from `POST /kernel/cycle`. **VERIFIED — DAK's output is consumed.**
- However — this entire chain lives inside `services/observation-runtime` (port 8090), which is **architecturally isolated** from `services/nvs-runtime` (port 8020, the actual NVS→CLE→HEKB pipeline traced in §4). Zero cross-references confirmed bidirectionally. So: DAK is real, wired, and consumed — but **only within a silo that the main pipeline never touches.** Net practical effect matches the spirit of the prior claim ("DAK doesn't affect the observation pipeline") even though its literal wording was wrong.
- `sensos-docs` (RFC-NVS-0206) documents a **different, more elaborate** DAK spec — "Dynamic Abort Kernel," a `HiddenStateAdapter` ABI attached to an LLM inference runtime — whose "detailed algorithms are proprietary... not reproduced" in the public doc repo. This is **NOT_EVALUABLE**: the spec'd DAK and the implemented `TrajectoryDifferentialSafetyKernel` may or may not be the same lineage; no repo in this audit contains code matching the `HiddenStateAdapter`/`DAKHook` contract described in RFC-NVS-0206.

---

## 13. HEKB Audit

**Repo: `hekb`** (confirmed via `git remote -v` → `git@github.com:GemminAI/hekb.git` — distinct from "sensos-hekb").

- Identity: content-addressed (BLAKE2b-256) object store + typed relation graph, dual Python (`hekb-api`, port 8080) / C++ (`hekbd`, port 8100) implementation, Python normative. **VERIFIED.**
- `POST /v1/objects` and `GET /v1/objects/{id}` are real (non-stub) in both stacks. `nearest`/`neighbours`/`geodesic` retrieval are real, implemented algorithms (linear k-NN, BFS, Dijkstra). Only `POST /v1/closure` is an explicit, self-documented stub. **VERIFIED.**
- The Python `hekb-api` (port 8080) is the best-evidenced match for the v1.0 report's "HEKB API on Mac" (`docs/hekb-api.md` explicitly ties port 8080 to `sensos`'s `hekb_url` default). **VERIFIED (port/config match); live-listener presence not probed.**
- MCP server (`hekb-mcp`, 7 real tools: put/get/relate/nearest/neighbours/geodesic/stats) exists and is **unrelated** to the `/home/parallels/sensos-cle/knowledge/mcp/` path from the DEPLOYMENT.md doc — that path belongs to `sensos-cle`'s (unfetched, upstream-only) Knowledge Plane commit, a different codebase entirely. **VERIFIED, CONTRADICTED as the same thing.**
- **Zero outbound calls to CLE/NVS/GPT-OSS anywhere** — this repo's own docs state the design intent explicitly: "HEKB stores. NVS-Kernel decides... The dependency arrow points one way." Purely passive storage, by design. **VERIFIED.**
- Read-back loop: **documented as intended** (`docs/NVS-Kernel.md`: NVS-Kernel is meant to write then later retrieve via `nearest`/`neighbours`), but **not confirmed wired** in either `nvs-kernel` or `sensos`. A cross-repo check found `sensos/integrations/hekb-mcp/client.py` does define read/query methods (`get_object`, `query_neighborhood`, `query_geodesic`) — but uses **integer object IDs**, which is **incompatible** with this `hekb` repo's 64-hex content-addressed ID scheme. This strongly suggests `sensos`'s HEKB-read integration either targets a **different HEKB backend** than the one audited here, or is stale/never-exercised code. **CONTRADICTED / UNVERIFIED — read-back capability exists somewhere, but not confirmed wired to this specific implementation.**
- Semantic ABI envelope fields (`semantic_abi_version`, `sir_version`, `stable_id`, `provenance`, `source_rfc`, `compiler_version`, per SIR-COMPAT-03): **explicitly and deliberately absent.** `docs/ABI.md`: "There is no `risk` field, no `tier`, no `provenance`... Provenance and lineage are `labels` and morphisms respectively." Object schema is a closed 6-field struct (`kind`, `created_ns`, `vector`, `attributes`, `labels`, `id`) with only `hext.object/1` as a version-like tag. **CONTRADICTED relative to SIR-COMPAT-03's mandatory envelope — any V2 JCS/SIR work must add a translation layer or accept a schema migration.**

---

## 14. sensos-cle vs. categorical-lift-engine Distinction

Fully established as two independent, non-interoperable implementations. See §3 table and §6 for details. Additional finding: `sensos-cle`'s local checkout (HEAD `9fa1d68`) is **2 commits behind `origin/main`**; the unfetched tip (`68f0773`, "Knowledge Plane v1.0.0") adds an entirely separate Python `knowledge/` subsystem (RFC compiler → linker → Unified Semantic Graph → MCP stdio server) that is **additive and explicitly self-scoped as non-modifying to the C++ CLE Runtime** ("Runtime impact: None — CLE Runtime remains frozen," per that commit's own docs). This explains the previously-confusing `DEPLOYMENT.md` document (§ of reference docs), which describes exactly this `knowledge/mcp/server.py` — it refers to a real but **not-yet-locally-fetched** state of `sensos-cle`, not to `categorical-lift-engine` or to a phantom system. **VERIFIED.**

HEXT in `sensos-cle`: `struct HextTensor { shape: vector<size_t>; data: vector<double>; }` — a numeric FP64 tensor, not a semantic/meaning-bearing object. **VERIFIED — matches expectation (b) from the audit brief, not (a).**

---

## 15. Semantic ABI / JSON / JCS Audit

- `03-semantic-abi-compatibility.md` (SIR-COMPAT-03) mandates a 6-field envelope (`semantic_abi_version`, `sir_version`, `stable_id`, `provenance`, `source_rfc`, `compiler_version`) on every SIR object, binding on Runtime/HEKB/MCP/Studio/GPT-OSS.
- **This envelope is implemented in zero of the audited repositories.** `hekb`'s schema explicitly and by design excludes several of these fields (§13). `nvs-mcp` has none of them (§9). No agent, across any of the seven independent audits, encountered `semantic_abi_version`, `sir_version`, or `stable_id` in any repository's actual code. **NOT_IMPLEMENTED workspace-wide, as far as this audit's coverage reached.**
- `SPEC-SENSOS-RTV2-JSON-002` (JCS/RFC 8785, `payload_hash`/`event_hash`, `contract_version`) is a **draft protocol specification with worked examples only** — no sub-audit was specifically tasked with grepping for `payload_hash`/`contract_version`/JCS implementation across all repos, so this is **NOT_EVALUABLE with a documented gap**, not a confirmed absence. Weak negative evidence: none of the seven broad audits incidentally surfaced these terms while grepping adjacent territory (HTTP clients, schemas, envelopes). Treat as **UNVERIFIED, leaning NOT_IMPLEMENTED**, and re-check explicitly before any V2 wire-protocol work begins.
- Per the SIR-COMPAT-03 document's own rule (§1.5): "Runtime, HEKB, MCP, Studio, and GPT-OSS MUST agree on the abstract model" — since HEKB's schema already conflicts with the mandatory envelope, **the JCS/SIR work cannot simply be laid on top of the existing HEKB `hekb` repo without either a migration or a translation/adapter layer.** This is a structural, not cosmetic, gap.

---

## 16. Existing Experiment Reclassification

Two genuinely different "closed loop" experiments exist in the historical record, and they must not be conflated:

1. **`EXP-Ubuntu012` (sensos v1.0 production integration, PDF §5.3)** — reclassified per this audit as: **"NVS-geometry-to-CLE-passthrough-to-HEKB-storage experiment."** It is **not** a semantic-grounding experiment: CLE's `/lift` received a 65-dim numeric position vector from NVS, never raw narrative text, and `build_hekb_object()` performed only a field rename/type-coercion (PDF §9: "no new HEKB schema, endpoint, or embedding was introduced"). This matches the exact "Raw Text → NVS hash projection" failure mode the audit brief (§13) warned against — it should be renamed accordingly wherever it is cited as evidence of "semantic" integration.
2. **`EXP-HEKB002` ("Full closed loop: MM→MSR→CLE→HEKB→query→MSR reuse," PDF Table 1, component phase)** — this **is** a genuine Meaning-Mapper → MSR → CLE → HEKB chain, run against a standalone `HEKBv2` workspace with editable installs of `meaning-space-runtime` and `categorical-lift-engine` — **but it was never integrated into the production `sensos` runtime.** It validates that the four components *can* compose (structurally, via Python Protocols per `meaning-space-runtime`'s own design — §11), not that they *do* compose in the live system. Its historical PASS result is real and should be preserved as evidence that the individual components are compatible in isolation, but must not be cited as evidence that the production pipeline performs semantic grounding — it does not (see #1).
3. **`/ground`-timeline correction (categorical-lift-engine, §6):** the vault "Architecture Gap Audit"'s claim that `/ground` 404s live was made using an OpenAPI probe **that predates `/ground`'s existence in source by roughly 23 minutes of commit history** (per git timestamps) — or possibly predates a later redeploy entirely. Any experiment or document citing that specific 404 finding as still-current must be re-verified with a fresh live probe before being trusted.

No agent found any file or test matching `TCK-v1`, `TCK-v2`, or `test_compatibility_kit` in any of the 13 repos. The prior gap-audit's claim that no TCK framework exists is **not contradicted by this audit** (carried forward, not independently re-derived from a repo-wide search in this pass).

---

## 17. V1 → V2 Gap Matrix

| Edge (v2 candidate) | Status | Evidence |
|---|---|---|
| Raw Narrative → Meaning Mapper | NOT_CONNECTED | meaning-mapper takes a `HEXTObservation`, not raw text; zero production callers found anywhere (§7) |
| Meaning Mapper → CLE | PROVISIONAL | Real HTTP client exists (`meaning_mapper/cle/client.py`, added 2026-08-12) but no live wire trace or production caller confirmed |
| Raw Narrative → CLE | PROVISIONAL (code) / NOT_CONNECTED (production) | `/ground` is real, routed, tested (§6) — but `sensos`'s production pipeline never calls it; it calls `/lift` with NVS output instead |
| CLE → NVS | NOT_IMPLEMENTED | No outbound HTTP client in `categorical-lift-engine`; only a structural DI Protocol, never invoked as a network call (§6) |
| NVS → CLE | VERIFIED (reverse of candidate direction) | This is the **actual, wired, production** edge (§4) |
| NVS → GPT-OSS | NOT_CONNECTED | Zero code found in any audited repo (§10) |
| GPT-OSS → NVS | NOT_CONNECTED | Same |
| NVS → 38 Ports | VERIFIED as intra-service capability | 38-Port registry lives inside `nvs-kernel` itself (§8, §11) — not an inter-service edge as the v2 diagram implies |
| 38 Ports → GPT-OSS | NOT_CONNECTED | No evidence found |
| 38 Ports → DAK | NOT_CONNECTED | DAK operates on independently-computed trajectory metrics (curvature/entropy/similarity), not on 38-Port API output (§12) |
| DAK → GPT-OSS | UNVERIFIED | DAK's decision does drive `KernelExecutive`'s own LLM cycle (real), but the LLM backend used is not confirmed to be GPT-OSS specifically (§10, §12) |
| DAK → 38 Ports | NOT_CONNECTED | DAK and the 38-Port registry live in different, non-cross-referencing services |
| NVS → HEKB (direct) | NOT_CONNECTED | No direct edge; HEKB write is always mediated through CLE's `lift_result` (§4) |
| CLE → HEKB | VERIFIED | Real, wired, best-effort (non-blocking) edge in production `sensos` (§4) |
| HEKB → Runtime (read-back) | CONTRADICTED / UNVERIFIED | Read/query API is real in `hekb`; a `sensos`-side client exists but uses an incompatible ID scheme, casting doubt on which backend it actually targets (§13) |
| HEKB → GPT-OSS | NOT_CONNECTED | No evidence |
| NVS-MCP → NVS | VERIFIED (code) / NOT_EVALUABLE (live) | Real HTTP adapter with silent offline fallback (§9) |
| NVS-MCP → HEKB | VERIFIED (code) / NOT_EVALUABLE (live) | Real 3-tier adapter, defaults to in-memory offline blob (§9) |
| NVS-MCP → GPT-OSS | NOT_CONNECTED | No GPT-OSS provider in `nvs-mcp` (§9) |

---

## 18. VERIFIED Runtime Graph

Only edges confirmed by direct code inspection, wired and reachable in the current production `sensos` repo:

```
[Observation Event]
       │ VERIFIED (api/routes.py → EventService.ingest)
       ▼
[Redis Outbox]
       │ VERIFIED (ForwardWorker.drain_once)
       ▼
[NVS-Kernel /observe]  (nvs-kernel repo, GCP :8100)
       │ VERIFIED (geometry.position passed as-is)
       ▼
[CLE /lift]  (categorical-lift-engine repo, GCP :8000)
       │ VERIFIED (best-effort, non-blocking; field rename only)
       ▼
[HEKB /v1/objects]  (hekb repo, Mac :8080)
       (chain terminates — no read-back confirmed wired)
```

Separately, unconnected to the above:

```
[LLM Cycle Request]  (services/observation-runtime, port 8090)
       │ VERIFIED
       ▼
[DAK: TrajectoryDifferentialSafetyKernel.evaluate()]
       │ VERIFIED (real branch: CONTINUE/CORRECT/RETRIEVE/ESCALATE/ABORT)
       ▼
[KernelExecutive control flow]  (rewrites prompt / aborts cycle)
```

And, structurally validated but never wired into either of the above:

```
[Meaning Mapper] --(Protocol shape only, no import)--> [MSR] --(Protocol shape only)--> [CLE] --(real HTTP)--> [HEKB]
```

---

## 19. Candidate V2 Runtime Graph

Reproduced from §5 for reference. **None of it should be treated as built.** The single edge in this diagram that is closest to already existing is `CLE (grounding) → NVS`, because CLE's `/ground` route is real and tested — but even that edge has never been called with NVS as the recipient of its output; it simply has never been wired to anything downstream at all.

---

## 20. Blocking Gaps (Top 10)

1. **Production pipeline never calls `/ground`.** CLE's real, tested 5W1H grounding endpoint is bypassed entirely; the runtime sends NVS's numeric geometry to `/lift` instead of raw narrative to `/ground`. This is the single highest-leverage, lowest-effort fix available (see §21).
2. **GPT-OSS integration location is unconfirmed**, not merely unwired — this blocks every downstream claim in the v2 pipeline (`GPT-OSS → 38 Ports`, `DAK → GPT-OSS`, etc.) simultaneously.
3. **38-Port API has zero callers from the production runtime.** `cognitive-port-selector` is a standalone LLM↔CPS↔NVS-Kernel loop, itself not wired into `sensos`.
4. **DAK is real and consumed — but trapped in an isolated silo** (`observation-runtime`, port 8090) that the main NVS→CLE→HEKB pipeline (port 8020) never touches.
5. **HEKB read-back is unverified against the correct backend.** `sensos`'s own HEKB-read client uses an ID scheme incompatible with the audited `hekb` repo's content-addressing — either a different backend is targeted, or the integration is stale.
6. **Meaning Mapper is architecturally orphaned** — fully implemented and tested, zero production consumers anywhere in the 13-repo workspace.
7. **Name collisions across "CLE," "HEKB," and "nvs-runtime"** create real traceability risk: any v2 spec, PR, or conversation that says "CLE" or "HEKB" without a repo+commit pin is ambiguous by construction, and this ambiguity has already caused at least one prior audit document (`DEPLOYMENT.md`) to appear inconsistent with the codebase it described.
8. **Semantic ABI / SIR envelope is implemented nowhere**, and `hekb`'s existing schema is explicitly incompatible with several mandatory fields — this is a migration problem, not a greenfield one.
9. **The 38-Port "source of truth" may not be internally consistent** even within existing code — `cognitive-port-selector`'s own discrepancy report (not independently re-verified here) claims its port snapshot disagrees with `nvs-kernel`'s live set in multiple places.
10. **No TCK-v1/TCK-v2 test harness exists anywhere** — every "PASS" cited in prior validation reports was measured by bespoke, per-repo EXP harnesses, not a shared, versioned compatibility kit; there is currently no regression net for any cross-repo wiring work.

---

## 21. Minimum Required Changes

Not implementation — this section only names the smallest concrete, evidence-backed first step, per the audit brief's requirement (§21/§12 "V2で最初に直すべき1箇所"):

**First fix, by repo and file:**
- `sensos` / `services/nvs-runtime/runtime/services/event_service.py` (or `forward_worker.py`) — currently sends the raw observation event straight to the Redis Outbox → NVS `/observe`, without ever touching CLE. This is where a call to CLE's `/ground` (raw text in) would need to be inserted, upstream of the existing NVS call.
- `sensos` / `services/nvs-runtime/runtime/gateway/cle_client.py` — currently implements only `lift()`. A `ground()` method calling `categorical-lift-engine`'s already-real `/ground` endpoint would need to be added.
- `categorical-lift-engine` needs **no new code** for this first step — `/ground` already exists, is routed, and is tested. This is the reason it is the lowest-effort, highest-leverage starting point: the missing piece is entirely on the `sensos` orchestration side, not in CLE itself.

This does **not** by itself achieve the full v2.0 candidate pipeline (GPT-OSS/38-Port/DAK integration remain separate, larger efforts per §20 items 2–4), but it is the one change that directly resolves the core architectural inversion this audit was commissioned to investigate.

---

## 22. Open Questions

1. Is `LOCAL_LLM_BASE_URL` (found in `sensos`'s `.env` variable list) actually pointed at a GPT-OSS instance? Unconfirmed — would resolve part of §10/§20 item 2.
2. Where do the "`sensos_cle_gptoss_*`" MLX scripts (per the prior gap-audit) actually live? Not found in any of the 13 repos audited here.
3. Was `nvs-kernel` checked for GPT-OSS integration by name? **No** — this audit's `nvs-kernel` sub-task focused on 38-Port/physics verification and did not grep for `gpt-oss`/`gptoss`. Flagged as a coverage gap; recommend a follow-up targeted grep.
4. Does `cognitive-port-selector`'s `DISCREPANCY_REPORT.md` accurately describe disagreement with `nvs-kernel`'s live port set, and how severe is it? Not independently re-verified in this pass.
5. Is `SPEC-SENSOS-RTV2-JSON-002` (JCS/`payload_hash`) implemented anywhere? No dedicated grep was run across all 13 repos for `payload_hash`/`contract_version`/JCS terms — recommend a follow-up pass before any V2 wire-protocol work begins.
6. Which HEKB backend does `sensos/integrations/hekb-mcp/client.py`'s integer-ID scheme actually target, if not the audited `hekb` repo? Unresolved — could be `sensos-hekb` (not locally present) or stale/dead code.
7. Is the live GCP `categorical-lift-engine` deployment (`34.61.86.172:8000`) currently running a build that includes `/ground` (post-`b8f6781`)? No fresh live probe was performed in this audit.
8. What is the actual relationship between the RFC-NVS-0206 "Dynamic Abort Kernel" spec (in `sensos-docs`) and the implemented `TrajectoryDifferentialSafetyKernel` (in `sensos`)? Same lineage, different implementation stage, or unrelated systems sharing an acronym? Unresolved.

---

## 23. Evidence Index

- **Primary validation document**: `SensOS_Runtime_v1_Integrated_Validation_Report.pdf` (pp. 1–16 read in full) — source of the confirmed V1 NVS→CLE→HEKB dataflow, commit `ce423a5`, HTTP status codes, latency figures, boundary audit.
- **Specification documents (candidate, not built)**: `SensOS Runtime v2.0 Integration Contract.md` (SPEC-SENSOS-RTV2-001), `SPEC-SENSOS-RTV2-JSON-002.md`, `Categorical Architecture Specification.md` (SPEC-SENSOS-KNOWLEDGE-CORE-001), vault `CLAUDE.md`.
- **Prior gap audit (re-verified against, not trusted)**: vault `Architecture Gap Audit.md` (SPEC-SENSOS-RTV2-GAP-001, 2026-08-14) — several claims reconfirmed (38-Port zero callers, GPT-OSS isolation), several corrected (DAK file path and "no caller" claim), one contradicted outright (`/ground` 404 — timeline mismatch identified).
- **Component validation reports**: `CLE-SPEC-01_Integrated_Validation_Report.md`, `CLE-HEKB-SPEC-01_Integrated_Validation_Report.md`, `HEKB-SPEC-01_Integrated_Validation_Report.md` — establish that `sensos-cle`/`sensos-hekb`/`sensos-cle-hekb` are a calibration-suite family distinct from the production runtime; `sensos-hekb` and `sensos-cle-hekb` have no local clone in this workspace.
- **Semantic ABI rules**: `03-semantic-abi-compatibility.md` (SIR-COMPAT-03) — mandatory envelope fields checked against `hekb` and `nvs-mcp` schemas and found absent (§15).
- **Deployment doc**: `DEPLOYMENT.md` — initially appeared inconsistent with `sensos-cle`'s checked-out state; resolved as describing an unfetched upstream commit (§14).
- **Direct code evidence**: file:line citations throughout §§4, 6–14 are drawn from seven independent sub-audits of `sensos`, `categorical-lift-engine`, `meaning-mapper`, `hekb`, `nvs-mcp`, `sensos-cle`, and the seven newly-identified adjacent repos (`nvs-kernel`, `cognitive-port-selector`, `hext`, `semantic-annotator-core`, `meaning-space-runtime`, top-level `nvs-runtime`, `sensos-docs`), each performing direct source/git/config inspection with no network access and no code modification.
- **Not performed in this audit**: live HTTP/wire-trace probes against any deployed endpoint (GCP `34.61.86.172:8000/8100`, Mac `10.211.55.2:8080`); a workspace-wide grep for JCS/`payload_hash` terms; a GPT-OSS-specific grep of `nvs-kernel`. These are named explicitly rather than silently assumed — see §22.

```
[END OF AUDIT: SENSOS-RTV2-XAUDIT-001]
```
