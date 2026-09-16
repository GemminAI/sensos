# SensOS 5 Repository Function Audit
**Date**: 2026-08-17
**Scope**: `/Users/tomonam3/GemminAI/{meaning-mapper, meaning-space-runtime, sensos-cle, nvs-runtime, cal}`
**Method**: read-only; no code changes; every claim below is corroborated by code (file:line), an actual test result, or an actual git fact — not by README/RFC text alone unless explicitly marked "claimed only."

---

## 1. Executive Summary

All five repositories are independent, self-contained Python/C++ **libraries** — none is a running service, none has a server process, and (with one real exception) none actually calls another of the five at runtime. They represent five genuinely different research instruments built at different times for different narrow purposes, connected today mostly by shared vocabulary in documentation, not by code:

- **meaning-mapper** (v2.3.0): a measurement library — HEXT Observation → `MeaningMeasurement` (θ, σ). The one **real, tested, live-callable** cross-repo connection found in this whole audit: its `cle/` subpackage is a working HTTP client for `categorical-lift-engine` (a sixth, unaudited repo).
- **meaning-space-runtime** / `msr` (pyproject 0.1.0, docs claim 1.1.0): a physics-style state-evolution library (Gaussian-well field, Langevin dynamics, stabilization detection). Fully implemented and tested (106/106 passing) against its own RFC, but every external connection (to HEKB, CLE, NVS-Kernel) exists only as an unimplemented `Protocol` port plus a non-normative test stand-in.
- **sensos-cle** (GemminAI clone, v0.5.0, **stale by one commit** relative to `Projects/sensos-cle`): a C++ payload/telemetry codec plus calibration/transport/discovery/certificate pipeline. Confirmed to still be, in substance, unrelated to the actual categorical-lift-engine math, despite the name.
- **nvs-runtime** (GemminAI clone, v1.0.0, **byte-identical** to `Projects/nvs-runtime` — same remote, same HEAD): a provider-agnostic runtime scaffold (discover/plan/invoke/observe/session/checkpoint). Every provider is an offline stub; no real network call exists anywhere in the package.
- **cal** (v0.1.0): **not** a calibration tool despite the name — "CAL" = Capability Adaptation Layer, a pure, dependency-free negotiation function (Intent × Capability × Environment → ranked action projections), per RFC-CAL-003.

The single strongest cross-repo naming trap found: **three unrelated things are all called "CLE"** (§10). The second: **`cal` sounds like "calibration" but the actual calibration work lives in `sensos-cle`**, not `cal`.

---

## 2. meaning-mapper

### Purpose
Takes a HEXT Observation and produces a `MeaningMeasurement` (position θ with declared uncertainty σ) for a downstream consumer — a pure measurement instrument with no state, no control, no language rendering. (`README.md:1-8`, `docs/BOUNDARIES.md:1-10`)

### Actual Functions
- 8-stage measurement pipeline: validate → raw features → metric tensor → local frame → density → covariance → projection → topology consistency (`src/meaning_mapper/pipeline.py:66`, `MeaningMapperPipeline.process()`)
- `cle/` subpackage: a real HTTP client (`CLEClient`, `src/meaning_mapper/cle/client.py:39`) with `.health()/.ground()/.lift()/.pullback()/.recover()/.compress()`, plus `ground_observation()` (`cle/grounding.py:101`)

### Runtime Role
Library, imported not executed (no `[project.scripts]`, no server code). **Real, tested HTTP dependency on `categorical-lift-engine`**: `tests/conftest.py:14` hardcodes `CLE_REPO = Path(".../categorical-lift-engine")` and boots the real CLE FastAPI app via uvicorn for live integration tests (`tests/test_cle_integration.py`).

### Dependencies
- `categorical-lift-engine`: **real**, HTTP-only, tested (`src/meaning_mapper/cle/*`, `tests/test_cle_integration.py`)
- `meaning-space-runtime`/MSR: **claimed only** — extensive doc/comment references (`docs/BOUNDARIES.md`, `measurement/meaning_measurement.py:3-10`) to structural compatibility with `msr.abi.MeaningMeasurement`, but zero `import msr` anywhere
- `hekb`, `nvs-runtime`, `sensos-cle`, `cal`: no references found

### Status
**PARTIALLY_CONNECTED** — implemented and internally correct (146 tests); really connected to CLE; its MSR relationship is doc-level only.

### Evidence
`pyproject.toml:3` (v2.3.0), `src/meaning_mapper/cle/client.py:145` (`httpx.Client.request`), `tests/conftest.py:14`, `tests/test_cle_integration.py:19` (`test_ground_live`).

---

## 3. meaning-space-runtime (package `msr`)

### Purpose
"The dynamic Meaning Physics engine of SensOS" — evolves measurements into continuous trajectories under a field potential Φ, reporting to a kernel port each step and to a lift port once a trajectory stabilizes in a basin. (RFC-MSR01.md §1)

### Actual Functions
- `msr.field`: `GaussianWell`, `FieldPrior` (potential/gradient/basin detection) — `field.py:32,77`
- `msr.dynamics`: `InformationAssimilator` (Bayesian fusion), `LangevinFlow` (CFL-guarded stepping, raises `CFLViolation` rather than silently diverging) — `dynamics.py:40,84`
- `msr.stability`: `StabilizationDetector` (dwell-based) — `stability.py:41`
- `msr.runtime` / `msr.host`: `MeaningSpaceRuntime.ingest()/.advance()`, `MSRHost` — `runtime.py:68,159`, `host.py:36`
- `msr.ports`: `Protocol`s `KernelPort`, `LiftPort`, `FieldPriorSource` — declared, **not implemented** except by non-normative `msr.reference` test stand-ins (`reference.py:40,66,139`)

### Runtime Role
Standalone library awaiting an external host. Zero HTTP/socket/gRPC code anywhere (verified by grep, zero hits). Designed for injection (`MSRHost(runtime=..., kernel=..., cle=..., hekb=...)`) but nothing in this repo performs that injection with a real implementation.

### Dependencies
Zero actual imports of any sibling repo. `pyproject.toml` deps: `numpy>=1.26` only. ~40 references to "HEKB"/"CLE"/"mapper" — all conceptual (docstrings, `ReferenceHEKB` class names), never a real import.

### Status
**STANDALONE / IMPLEMENTED** (within its own declared scope) — 106/106 tests pass (re-run directly this audit), matches its own RFC closely; zero real cross-repo wiring.

### Evidence
`src/msr/ports.py:4` ("MSR imports no neighbour code" — verified true), `tests/test_properties.py:171,218`, `experiments/results/exp_msr_002.json` (real executed evidence of bootstrap-mode stabilization behavior).

**Note**: pyproject.toml/`version.py` say `0.1.0`; CHANGELOG.md and RFC-MSR01.md describe a "1.1.0" milestone. Version string was never bumped — flagged in §10.

---

## 4. sensos-cle (GemminAI clone — confirmed stale)

**Naming/staleness fact, stated up front**: `GemminAI/sensos-cle` and `Projects/sensos-cle` share one git remote (`git@github.com:GemminAI/sensos-cle.git`) but differ by at least one commit — `GemminAI`'s copy (HEAD `9fa1d683`, 2026-08-08) is missing `Projects`' newest commit (`68f0773`, "Knowledge Plane v1.0.0", 2026-08-09). This audit reflects the **older** state.

### Purpose
Reference/commercial C++ implementation of `CLE-SPEC-01`: a payload codec + calibration/transport/discovery/certificate pipeline, built so `EXP-CLE-0001…0004` pass and a `cle_calibration_certificate.json` can be issued. (`README.md:3-7`, `CHARTER.md:1-9`)

### Actual Functions
- Phase 1 codec: bit-exact FP64 HEXT↔token round-trip (`PayloadCodec`, `include/.../payload_codec.hpp:38-64`)
- Phase 2 calibration: `CalibrationExecutor::run_exp_cle_0002()` → `CalibrationReport`
- Phase 3 transport: byte-frame + SHA-256 + fragment/reassembly — **explicitly "No sockets/HTTP/gRPC/MCP"** (`docs/ARCHITECTURE.md:37`)
- Phase 4 discovery: internal Capability ABI registry/discover/resolve — **explicitly "not network discovery"** (`docs/ARCHITECTURE.md:41`)
- Phase 5 certificate: aggregates Phase 1-4 reports into `cle_calibration_certificate.json`, read-only
- `abi/reason_engine_v1/reason_engine.h`: a pure C11 ABI **contract**, explicitly "not a runtime implementation"

### Runtime Role
Static library (`add_library(sensos_cle_runtime ...)`, `CMakeLists.txt:9-34`) exercised only by its own in-tree test/experiment executables. Docker wraps `cmake+ctest`, not a served process.

### Dependencies
Zero code-level connections to any of the other four repos, `categorical-lift-engine`, or `34.61.86.172`. All cross-system mentions are **doc-level "must not own" boundary declarations** (`CHARTER.md:49`, `docs/BOUNDARIES.md:16-17`: "Does not own MSR, HEKB, NVS-Kernel...").

### Status
**STANDALONE.** Confirmed: the prior session's characterization ("payload/telemetry codec, unrelated to CLE's actual categorical-lift-engine algorithm") **still holds** at this commit — the repo has grown in breadth (added calibration/transport/discovery/certificate phases) but not in kind; no category-theoretic Lift/Recover/Pullback math anywhere.

### Evidence
`CMakeLists.txt:2` (`sensos-cle-runtime VERSION 0.5.0`), `tests/test_payload_codec.cpp` (`encoding_fidelity_pct == 100.0`), `experiments/README.md` ("specifications, not production measurement harnesses").

---

## 5. nvs-runtime (GemminAI clone — confirmed identical to Projects copy)

**Duplication fact, stated up front**: `GemminAI/nvs-runtime` and `Projects/nvs-runtime` are the **same git repository**, same remote (`git@github.com:GemminAI/nvs-runtime.git`), **same HEAD** (`9f6cb37e`) — two clones of one codebase, not competing implementations. Also distinct from, and unrelated in code to, `services/nvs-runtime` inside the separate `GemminAI/sensos` repo (the deployed FastAPI service this session's own work extended) — zero references either direction, confirmed by grep.

### Purpose
"A provider-agnostic runtime substrate for layer-oriented AI systems" — one stable API (`discover/plan/invoke/observe/session/checkpoint`) over swappable backend providers. (`README.md`, `docs/architecture.md`)

### Actual Functions
`NVSRuntime` (discover/plan/invoke/observe/session/checkpoint/metrics/shutdown — `core/runtime.py:47`), `CapabilityGraph`, `Planner`, `SessionManager`/`CheckpointManager`, `GovernanceEngine`, `CBACEngine`, `MetricsCollector`/`ObservabilityStore`/`EventBus`, six `providers/{local,http,grpc,mcp,kernel,hekb}.py`.

### Runtime Role
**Standalone / entirely offline.** Every non-local provider defaults to a deterministic in-process stub: `HttpProvider`/`GrpcProvider`/`McpProvider` all return `{"mode": "offline_stub", ...}` with **no real network library call anywhere in `src/`** (verified: no `requests`/`aiohttp`/socket code found); `KernelProvider` defaults `available=False` → `status: "DEFERRED"`, no host ever dialed; `HekbProvider` is backed by an in-memory dict store. The provider-guide's plugin/entry-point discovery is explicitly future work (`ROADMAP.md` v1.1), not implemented.

### Dependencies
Zero hits for any of the other four repos, `categorical-lift-engine`, `NVS-Kernel`, or `34.61.86.172`, anywhere in the package.

### Status
**STANDALONE.**

### Evidence
`pyproject.toml:2-3` (v1.0.0), `src/nvs_runtime/providers/http.py:33-44`, `tests/test_providers.py:36,78` (`test_http_offline_stub`, `test_kernel_deferred_without_daemon`).

---

## 6. cal

### Purpose
**Not calibration.** "CAL — Capability Adaptation Layer Negotiation Engine," reference implementation of RFC-CAL-003: given an Intent, a Capability Descriptor, and an Environment Context, deterministically compute up to 8 ranked candidate action "projections" — explicitly excluding final selection of one (deferred to RFC-CAL-004). (`pyproject.toml` description, `README.md` title)

### Actual Functions
4-stage pure pipeline in `negotiate()` (`cal/negotiation/service.py:19`): `prune()` (feasibility) → `map_affordances()` → `generate_candidates()` (≤8, deterministic hash-based IDs) → `score_candidates()` (feasibility/safety/confidence ∈ [0,1]). Domain coverage extends beyond robotics: `MobilityClass` includes `NARRATIVE`/`TRADING`; `IntentOpcode` includes narrative and trading opcodes.

### Runtime Role
**Standalone, pure-function library.** Explicitly documented and verified: "No I/O, global state, randomness, wall-clock, network, or LLM" (`cal/negotiation/service.py:24-28`). `dependencies = []` in pyproject.toml.

### Dependencies
Zero hits for any of the other four repos. One coincidental naming collision: docstrings reference an **unpublished spec** `RFC-HEKB-015` for its semantic-type vocabulary (`cal/types.py:45`) — this is a different thing from the `hekb` repository, not a code or API dependency on it.

### Status
**IMPLEMENTED / STANDALONE** — 40/40 tests pass (re-run this audit), matches its own experiment's validation report (`EXP-CAL-0001/validation_report.md`).

### Evidence
`cal/negotiation/service.py:19`, `tests/unit/test_ranking.py` (`test_ranking_stable_across_repeated_calls`), `experiments/EXP-CAL-0001/benchmark.py`.

**Note**: no git remote is configured on this local checkout (`git remote -v` returns empty) — the presumed GitHub origin could not be verified from this machine's clone.

---

## 7. Cross-Repository Responsibility Matrix

| Repository | Primary Purpose | Actual Functions | Current Runtime Role | Status |
|---|---|---|---|---|
| meaning-mapper | HEXT Observation → geometric meaning measurement (θ, σ) | validation, feature extraction, metric tensor, local frame, density, covariance, projection, topology check, CLE HTTP client | Library; real HTTP consumer of `categorical-lift-engine` | PARTIALLY_CONNECTED |
| meaning-space-runtime | Evolve measurements into stabilized trajectories under a field potential | Gaussian-well field, Langevin dynamics (CFL-guarded), stabilization detection, host/runtime orchestration of the above | Library; ports defined, no real implementations wired in-repo | STANDALONE / IMPLEMENTED (own scope) |
| sensos-cle (GemminAI) | CLE-SPEC-01 payload codec + calibration/transport/discovery/certificate pipeline | FP64↔token codec, calibration executor, byte-frame transport, internal capability-ABI discovery, certificate generator | C++ static library; exercised only by own tests/experiments | STANDALONE (stale clone, -1 commit) |
| nvs-runtime (GemminAI) | Provider-agnostic runtime substrate (discover/plan/invoke/observe/session/checkpoint) | Capability graph, planner, session/checkpoint managers, governance, CBAC, metrics/events, 6 provider stubs | Library; every provider is an offline stub, no live network call anywhere | STANDALONE |
| cal | Capability negotiation: Intent×Capability×Environment → ranked action projections | Prune, affordance mapping, candidate generation, scoring/ranking — pure function | Library; zero dependencies, zero I/O | IMPLEMENTED / STANDALONE |

---

## 8. Actual Dependency / Data Flow

Only connections with real code evidence are drawn as solid arrows; everything else found was documentation/comment-level only.

```
meaning-mapper ──(real, tested HTTP via httpx)──> categorical-lift-engine
                                                    [external repo, not audited this pass;
                                                     live-deployed at 34.61.86.172:8000
                                                     per this session's earlier audits]

meaning-mapper  <··(claimed structural compatibility, no import either way)··>  meaning-space-runtime

meaning-space-runtime  <··(unimplemented Protocol ports + non-normative
                            test stand-ins only)··>  HEKB, CLE, NVS-Kernel
                                                       [external, not audited this pass]

sensos-cle (GemminAI)   ── no verified connection to anything ──  (fully standalone)
nvs-runtime (GemminAI)  ── no verified connection to anything ──  (fully standalone)
cal                     ── no verified connection to anything ──  (fully standalone)
```

No connection was found, in either direction, between any pair of: {meaning-space-runtime, sensos-cle, nvs-runtime, cal}. No connection was found between meaning-mapper and {sensos-cle, nvs-runtime, cal}.

---

## 9. Function Ownership Matrix

| Function | Actual Owner (of the 5 audited) | Other Implementations Found | Duplication Risk |
|---|---|---|---|
| Meaning / Grounding | meaning-mapper (measurement); its `cle/` client calls the *external* `categorical-lift-engine` for actual grounding (`/ground`) | — | None among the 5 — meaning-mapper is the sole owner here |
| Semantic Transformation | meaning-mapper (8-stage pipeline) | — | None found |
| **Projection** | meaning-mapper (`project_to_theta()` — geometric embedding) **and** cal (`ProjectionSet`/`CandidateProjection` — ranked *action* candidates) | — | **Naming collision, not function duplication**: same word, two unrelated concepts (semantic-geometric projection vs. capability-action projection). No shared code, no shared consumer found |
| Geometry | meaning-mapper (metric tensor, local frame, topological consistency) | — | None among the 5 |
| Trajectory | meaning-space-runtime (`StabilizedTrajectory`, Langevin dynamics) | — | None among the 5 |
| Observation | none of the 5 *owns* this — meaning-mapper only *consumes* a "HEXT Observation" as input | (external: NVS-Kernel / `sensos/services/nvs-runtime`'s Observation ABI) | Not applicable within these 5 |
| **Calibration** | sensos-cle (GemminAI) — real `CalibrationExecutor`, real `cle_calibration_certificate.json` | — | **cal does NOT own calibration** despite the name — verified: "CAL" = Capability Adaptation Layer, unrelated function entirely |
| Capability Discovery | nvs-runtime's `runtime.discover()` (real API, but lists only offline-stub providers) **and** sensos-cle's Phase-4 internal ABI discovery (explicitly *not* network discovery) | (external: `sensos/services/nvs-runtime`'s `get_port_capability()` — real, live-verified, built this session, unrelated code to either of these) | Three same-named-concept implementations exist across the broader SensOS landscape; none of the 3 shares code with either of the others |
| Capability Negotiation/Adaptation | cal (sole owner — pure Intent×Capability×Environment→Projections function) | — | None found |
| Runtime Orchestration | nvs-runtime (self-describes as this; fully offline scaffold) **and** meaning-space-runtime (`MSRHost`/`MeaningSpaceRuntime` — narrower, physics-simulation-specific orchestration) | (external: `sensos/services/nvs-runtime`'s `capability_decision.py` — real, live-verified, built this session) | Same word "runtime" used for three structurally different things; zero code sharing among them |
| Evidence | none of the 5 | (external: HEKB + `sensos/services/nvs-runtime`'s `build_hekb_object_from_port_result()`) | Not applicable within these 5 |
| Lineage | none of the 5 | (external: `sensos/services/nvs-runtime`'s Event/`parent_event_id` chain) | Not applicable within these 5 |

---

## 10. Findings / Ambiguities

1. **Triple "CLE" naming collision** (the most consequential finding): (a) `sensos-cle` (this audit) — a C++ payload codec + calibration pipeline, explicitly *not* the categorical math; (b) `categorical-lift-engine` — the real category-theoretic Lift/Recover/Pullback engine, live at `34.61.86.172:8000` (external, not audited this pass, per this session's earlier findings); (c) `meaning-mapper`'s `cle/` subpackage — merely an HTTP *client* for (b), containing no CLE implementation itself. All three are real, current, and actively referenced in docs under the bare word "CLE" — high risk of conflation.

2. **`cal` ≠ calibration**: the name strongly suggests calibration; the actual repo is a capability-negotiation engine (RFC-CAL-003) with zero calibration logic. The real calibration work (certificates, calibration executor) lives in `sensos-cle`. Verified from both repos' actual code, not assumed from names.

3. **`nvs-runtime` (GemminAI/Projects clones) is unrelated in code to `sensos/services/nvs-runtime`** (the deployed FastAPI service this session's own work extended with `capability_decision.py` etc.) despite sharing the name exactly. Zero cross-references found in either direction.

4. **Disconnected-but-claimed relationships**: meaning-mapper ↔ meaning-space-runtime (both sides claim structural compatibility in docs/comments; neither actually imports or calls the other). meaning-space-runtime ↔ HEKB/CLE/NVS-Kernel (Protocol ports declared, zero real implementations in-repo, only non-normative test stand-ins).

5. **Stale local clone**: `GemminAI/sensos-cle` is missing at least one commit ("Knowledge Plane v1.0.0") present in `Projects/sensos-cle` — same remote, diverged local state. This audit reflects the older commit.

6. **Version-string drift**: `meaning-space-runtime`'s `pyproject.toml`/`version.py` still say `0.1.0` while its own CHANGELOG.md and RFC-MSR01.md describe a "1.1.0" milestone dated 2026-08-04 — the package version was never bumped to match.

7. **`cal` has no git remote configured** on this local checkout — the other four all have a verifiable `git@github.com:GemminAI/*.git` origin; `cal`'s could not be confirmed from this machine.

8. **Duplicate "Capability Discovery" concept, no duplicate code**: nvs-runtime's `discover()`, sensos-cle's Phase-4 internal ABI discovery, and this session's own `get_port_capability()` (in the separate `sensos` repo) are three independent implementations of a similarly-named idea, sharing no code, at three different levels of "realness" (fully offline stub / in-process-only / live-verified against a real external service, respectively).

9. **`cal`'s uncommitted local state**: `tests/__init__.py` has a pre-existing uncommitted one-line modification, present before this audit began — not touched, noted only.

10. No prompt-injection or AI-agent-directed override text was found in any of the five repositories.

---

## 11. Conclusion

These five repositories are five genuinely separate research instruments, each solving a narrow, different problem, built at different times: **meaning-mapper** measures raw observations into geometric coordinates and is the one repo with a real, tested, live external dependency (on `categorical-lift-engine`); **meaning-space-runtime** is a self-contained physics engine for evolving those coordinates into trajectories, fully implemented but never wired to a real host; **sensos-cle** is a C++ codec/calibration pipeline, standalone, confirmed unrelated to the categorical math its name suggests; **nvs-runtime** is a fully offline "runtime substrate" scaffold, standalone, and distinct in code from the similarly-named service this session built on; and **cal** is a pure, dependency-free capability-negotiation function, standalone, and — despite its name — has nothing to do with calibration. None of the five calls another of the five except the one meaning-mapper→categorical-lift-engine link; everything else resembling a connection between them exists only as shared vocabulary in documentation.

---

## Verification

No code was changed. Only this report file was created.

```
$ git status --short   (in /Users/tomonam3/GemminAI/sensos)
?? CLAUDE.md
?? docs/SENSOS_KNOWLEDGE_CORE_AND_CATEGORY_THEORY.md
?? docs/spec/SPEC-SENSOS-RTV2-JSON-002.md
?? experiments/
?? docs/audit/SENSOS_5_REPOSITORY_FUNCTION_AUDIT_20260817.md   <- this report
```
(The four other untracked items pre-date this audit; not created or touched by it.)

### HEAD of each audited repository (recorded, unmodified)
| Repository | HEAD | Remote |
|---|---|---|
| meaning-mapper | `9bea2196bc9b78d3295c45014e96c004bff74a95` | `git@github.com:GemminAI/meaning-mapper.git` |
| meaning-space-runtime | `6fc3d98a1865fd8ff220cbdf1918aedf09903d0b` | `git@github.com:GemminAI/meaning-space-runtime.git` |
| sensos-cle (GemminAI) | `9fa1d683f4b528653cee0d5a793e1ab69b968d48` | `git@github.com:GemminAI/sensos-cle.git` (stale vs. Projects copy at `68f0773`) |
| nvs-runtime (GemminAI) | `9f6cb37e990535427c032a232758b9ea5030a67d` | `git@github.com:GemminAI/nvs-runtime.git` (identical to Projects copy) |
| cal | `4f8c9cde081d83a28272d19335ecd6d6fb2f69b6` | none configured on this checkout |

All five: `git status --short` showed no changes made by this audit (cal's pre-existing single-line modification to `tests/__init__.py` predates this audit and was left untouched).
