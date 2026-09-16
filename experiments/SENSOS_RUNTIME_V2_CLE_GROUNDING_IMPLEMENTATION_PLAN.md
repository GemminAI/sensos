# SensOS Runtime v2.0 — CLE `/ground` → NVS Integration: Implementation Plan

**Document ID**: SENSOS-RTV2-PLAN-001
**Status**: Design only. No code, schema, Docker, or API changes have been made.
**Author role**: Implementation Lead, working from the Cross-Repository Architecture Audit (`SENSOS_RUNTIME_V2_CROSS_REPOSITORY_ARCHITECTURE_AUDIT.md`)
**Method**: Direct re-inspection of current source in `sensos`, `categorical-lift-engine`, and `nvs-kernel` this session. Nothing here is inherited from the prior audit without being independently re-read.

Status vocabulary: **VERIFIED** (read directly this session) / **PROVISIONAL** (inferred with a caveat) / **UNVERIFIED** (not checked this session) / **UNKNOWN** (genuinely open, needs a decision).

**Guardrail, stated once, binding for the rest of this document:** "CLE" below always means `/Users/tomonam3/GemminAI/categorical-lift-engine` (Python/FastAPI, has `/ground`). It is never `sensos-cle` (C++, no grounding, no HTTP). This distinction was the subject of a dedicated finding in the prior audit and is restated here so no reader conflates them while implementing.

---

## 1. Objective

Determine — from the actual current code, not from the v2 candidate diagram — how CLE's `/ground` endpoint could be inserted ahead of NVS-Kernel's `/observe` call in the production `sensos` runtime, as the first V2 vertical slice. This document is a design artifact only. It ends with an Implementation Gate; no implementation follows until that gate is met and the user has reviewed this plan.

---

## 2. Current V1 Call Graph (VERIFIED, re-read this session)

```
POST /sessions/{session_id}/events                                    [runtime/api/routes.py:82-84]
        │  EventIngestRequest{event_type, agent_id, payload: dict, ...}
        ▼
EventService.ingest()                                                 [runtime/services/event_service.py:19-97]
        │  builds `envelope` dict (event_id, session_id, sequence_id, payload, ...)
        │  unconditionally: self.redis.enqueue_forward(...) — no synchronous RPC (EXP-Ubuntu011)
        ▼
Redis Outbox (runtime:forward:queue)
        │
        ▼
ForwardWorker.drain_once()                                            [runtime/services/forward_worker.py:91-149]
        │  build_observation_event(envelope) — reads envelope["payload"]["text"]
        ▼
KernelGateway.observe_batch(session_id, events)                       [runtime/gateway/kernel_gateway.py:119-133]
        │  ──POST /observe──►  NVS-Kernel (nvs-kernel repo)
        │  ObserveRequest{session_id, events:[EventPayload{step,timestamp_ns,kind,text,
        │                   source,agent_id,tool,attributes:dict[str,str]}], include_vectors=True}
        ▼
ObserveResponse{session_id, cycle, control, geometry: {"position": [...], ...} | None}
        │
        ▼
ForwardWorker._propagate_semantic_mapping(session_id, response)       [forward_worker.py:151-182]
        │  geometry.position (NVS's own computed vector) — best-effort, non-blocking, runs
        │  only AFTER NVS forward already succeeded and is already FORWARDED
        ▼
CLEClient.lift(position)                                              [runtime/gateway/cle_client.py:48-61]
        │  ──POST /lift──►  categorical-lift-engine
        │  wraps `position` as ConceptInput{states:[{theta: position}]} — a numeric point,
        │  NOT raw text. This is the ONLY CLE call that exists in the runtime today.
        ▼
build_hekb_object(lift_result, position=position, session_id=..., cycle=...)  [hekb_client.py:24-70]
        │  field-rename/coercion only
        ▼
HekbClient.store()                                                    [hekb_client.py:96-103]
        │  ──POST /v1/objects──►  hekb repo, kind="OBSERVATION"
        ▼
   (chain terminates — no read-back)
```

Confirmed facts, re-verified this session:

- Raw text first enters the system as `EventIngestRequest.payload` (a free-form `dict[str, Any]`, `runtime/models/schemas.py:101-109`) — nothing in the schema names a `text` field explicitly; `build_observation_event()` reads `payload.get("text", "")` by convention (`kernel_gateway.py:85`).
- `ObservationEvent`/`EventPayload` (the wire shape sent to NVS) is **text + string-attributes only** — no vector field exists in this request today, on either the `sensos`-side model (`runtime/abi/observation.py:41-51`) or nvs-kernel's own server-side schema (confirmed independently in `nvs-kernel/nvs_kernel/api/schemas.py:27-35` — identical shape).
- `CLEClient.lift()` is the **only** existing CLE call anywhere in `sensos`. There is no call to `/ground` anywhere in the current codebase (re-confirmed this session by inspecting `cle_client.py` in full — it has exactly one route method, `lift()`, plus a generic `call()`).
- Construction order (from the prior audit, not re-verified again this session but consistent with the code read here): NVS wiring landed before CLE/HEKB wiring. CLE receives NVS's numeric output, never raw text, today.

---

## 3. CLE `/ground` Actual Contract (VERIFIED, re-read this session)

**Route**: `POST /ground`, registered at `categorical-lift-engine/src/cle/api/router.py:161-185`, included on the live FastAPI app (`api/app.py:33`, confirmed in the prior audit). No explicit `status_code=` override on the decorator → default FastAPI `200` on success.

**Request** (`GroundRequest`, `api/models.py:160-168`):

```python
class GroundRequest(BaseModel):
    prompt: str
    goal: str
    five_w1h_overrides: FiveW1HOverridesInput = FiveW1HOverridesInput()   # who/what/when/where/why/how, all optional
    sok_overrides: SOKOverridesInput = SOKOverridesInput()                # subject/observer/knowledge_reference, all optional
    default_knowledge_reference: str = "unspecified"
    embedding_dimension: int = Field(default=8, ge=1, le=64)
```

Both `prompt` and `goal` are **required, non-optional strings**. This matters — see §5's data-contract gap.

**Response** (`GroundResponse`, `api/models.py:171-186`):

```python
class GroundResponse(BaseModel):
    semantic_state: GroundedStateModel   # prompt, goal, five_w1h{6×{value,source}}, sok{...},
                                          # fingerprint/goal_fingerprint/subject_fingerprint/
                                          # observer_fingerprint/knowledge_fingerprint: list[str]
    lift: LiftResponse                   # concept_id, normalized_hash, morphisms, pullback_limit,
                                          # pushout_colimit, invariants{betti_0,1,2,euler_characteristic},
                                          # compression_ratio, semantic_closure, proof{...}
```

**Critical structural fact, confirmed by reading `grounding/service.py:37-65` directly:** `/ground` does not merely extract 5W1H — it **already calls `CLEEngine.lift()` internally**, using point clouds built by SHA-256-hashing character trigrams of the combined 5W1H text (`grounding/embedding.py`, `grounding/semantic_state.py:86-128`). This means `GroundResponse.lift` is a **complete, self-contained lift result computed entirely from CLE's own text-derived hash-embedding** — it has nothing to do with NVS's geometry. It is architecturally a *different* `LiftResponse` than the one `ForwardWorker._propagate_semantic_mapping()` currently obtains by calling `/lift` with NVS's `geometry.position`. **These two lift results must never be conflated or treated as the same measurement** — one is "CLE's own opinion of the text, before NVS ever sees it," the other is "CLE's re-interpretation of NVS's already-computed physics." Any design below that calls `/ground` produces a second, independent lift result alongside the existing one, not a replacement.

**Determinism**: `five_w1h.py` — regex-only, no LLM call (re-confirmed: no LLM/HTTP-out import in `grounding/*.py` besides the outbound structure itself). `embedding.py` — SHA-256 trigram hashing, explicitly disclosed as "not a semantic embedding model" in its own docstring. **VERIFIED.**

**Error handling inside CLE**: `router.py`'s own comment states exceptions propagate as `cle.errors.CLEError` subclasses, translated to HTTP responses by handlers registered in `cle.api.app`. **UNVERIFIED this session** — `cle/api/app.py`'s exception-handler registrations were not read. Treat CLE-side validation-error status codes as **UNKNOWN** until that file is read; the plan below assumes only that `CLEClient.ground()` will need the same `_TRANSPORT_ERRORS` handling `lift()` already has, not that CLE-side 4xx/5xx semantics are fully characterized.

---

## 4. NVS `/observe` Actual Contract (VERIFIED, re-read this session — nvs-kernel repo, not sensos's client-side mirror of it)

**Route**: `POST /observe`, `nvs-kernel/nvs_kernel/api/routers/pipeline.py:70-120`.

**Request** (`ObserveRequest`, `nvs-kernel/nvs_kernel/api/schemas.py:38-44`):

```python
class EventPayload(_Schema):
    step: int = 0
    timestamp_ns: int = 0
    kind: str = "OBSERVATION"
    text: str = ""
    source: str = "api"
    agent_id: str = "unknown"
    tool: str | None = None
    attributes: dict[str, str] = {}

class ObserveRequest(_Schema):
    session_id: str
    events: list[EventPayload]
    adapter: str = "generic"
    approval_token: str | None = None
    horizon_steps: int | None = None
    include_vectors: bool = False
```

**There is no vector, embedding, or structured-object field anywhere in this request schema.** `text` and `attributes: dict[str, str]` are the only content-bearing fields. This is the server's real, current wire contract — independently confirmed by reading nvs-kernel's own schema file, not inferred from `sensos`'s client-side mirror of it.

**How position is actually computed** (`nvs-kernel/nvs_kernel/runtime/pipeline.py:200-208`):

```python
def observe(self, session, events):
    observations = tuple(self._observation.observe_many(events))
    for observation in observations:
        session.stream.append(observation)
        session.record_position(self.project(observation.text))   # <-- always from .text
    return observations

def project(self, text: str) -> Vector:
    return self._manifold.project_point(self._projector.project(text))
```

The configured `Projector` is, by default, `HashingProjector` (`nvs_kernel/projection/hashing.py`) — deterministic, signed BLAKE2b feature-hashing over token 1/2-grams and character 3-grams. This is structurally the **same class of technique** CLE's own `embedding.py` uses (disclosed hash-embedding, not a semantic model) — just a different algorithm/parameterization, computed independently. A `PrecomputedProjector` also exists in the codebase (`projection/hashing.py:113-149`), which *would* accept an externally-supplied vector — but only via a direct in-process `.accept(values)` call; **there is no HTTP path that reaches it**, because `EventPayload` has no vector field to route into it.

**Conclusion, stated plainly because it changes the shape of every option below:** *Under the current wire contract, NVS-Kernel always computes its own position from `text`, and there is no way — without changing NVS's schema and/or its projector configuration — for an externally-computed vector (CLE's `GroundedState` point cloud, or anything else) to influence what NVS's `/observe` actually produces.* The candidate architecture's arrow "`GroundedState → NVS`" cannot be made literally true this round, because doing so requires an NVS-side change, which is out of scope per the task's own constraint (§7 of the task brief: "38 Portsは今回まだ接続しない"/"HEKBも今回まだ変更しない" — and by the same logic and explicit instruction elsewhere in the brief, NVS is also not to be changed this round). This is reported honestly rather than designed around silently.

---

## 5. Current Gap

1. **No wire path exists for CLE's grounded representation to reach NVS's geometry computation.** (§4, above — the load-bearing finding of this plan.)
2. **No call to `/ground` exists anywhere in `sensos` today.** `CLEClient` has only `lift()`.
3. **`GroundRequest.goal` has no natural source in the current runtime.** `EventIngestRequest`/`ObservationEvent` carry `text`, `source`, `agent_id`, `tool`, `attributes` — nothing resembling a "goal." This is a genuine, unresolved mapping gap (see §9, §15 — not decided unilaterally here).
4. **Two independent "lift" computations would coexist** if `/ground` is called: CLE's own text-hash-derived lift (from grounding) and the existing NVS-geometry-derived lift (from the current `/lift` call). Nothing today distinguishes them if both are stored without a discriminating label.
5. **The current CLE/HEKB leg is deliberately best-effort/silent-on-failure** (`forward_worker.py:171-181`, log-and-swallow). The task brief explicitly flags this pattern as risky for a grounding step, because whether grounding succeeded or was silently skipped could affect what a downstream reader believes was measured. This needs a considered answer, not a copy-paste of the existing pattern (§10).

---

## 6. Candidate Integration Designs

### A. Grounding-as-parallel-audit-capture (NVS input unchanged)

Call CLE `/ground` with the raw narrative text, in the `ForwardWorker` background path, **before** (or concurrently with, order-wise upstream of) the existing `observe_batch()` call. NVS still receives the **exact same** `text` it receives today via `EventPayload.text` — nothing about NVS's request changes. The resulting `GroundedState` + its own (text-derived) `LiftResponse` are captured as a correlated artifact (see §9 for exactly where), keyed by `event_id`/`session_id`/`sequence_id`, alongside — not instead of — the existing NVS→CLE(`/lift`)→HEKB flow.

- **What it achieves**: the literal *ordering* the audit recommended ("CLE grounding happens before NVS observation" is now true in wall-clock/call-order terms), plus a real, working, tested `/ground` call path in `sensos` for the first time.
- **What it does not achieve**: NVS's actual geometry is not "grounded" — it is computed exactly as before. This must be stated to anyone reading results downstream.
- **Risk profile**: lowest. Zero change to NVS's input, zero change to CLE, zero change to HEKB's schema. Fully additive; a grounding outage cannot affect the existing V1 pipeline's behavior at all, because nothing existing reads the grounding output as an input to anything else this round.

### B. Canonicalized-grounded-text substitution

Call `/ground`, build a canonical string from `five_w1h` (e.g. `"who: {who} | what: {what} | when: {when} | where: {where} | why: {why} | how: {how}"`), and send **that** string as `EventPayload.text` to NVS instead of the original raw narrative — using NVS's existing text-only wire contract exactly as-is (no NVS-side change needed to *accept* this).

- **What it achieves**: in a shallow, literal sense, NVS's position now depends on something CLE computed — the "arrow" in the v2 diagram is drawn, technically, without touching NVS's code.
- **What it risks — stated explicitly, per the task brief's own instruction to flag this**: `HashingProjector` has no semantic understanding; it hashes literal surface tokens. A short, templated 5W1H summary string contains far less of the original narrative's actual vocabulary than the raw text did, so:
  - Two materially different real narratives that happen to reduce to similar 5W1H fields (a real risk, since `who`/`what`/`why`/`how` are often short, generic derived substrings — see `five_w1h.py:85-88`) would produce **closer or identical geometry**, which is a loss of discriminating power, not a gain, for an *observation* system whose stated job is to detect state, not to normalize it away.
  - Every V1 position ever recorded was computed from raw text; switching to canonical-text input for new events breaks direct comparability with all prior geometry without a migration/dual-write plan.
  - CLE becomes a **hard dependency of NVS's own core function** (not just of the downstream HEKB write), even though `runtime/core/config.py`'s own comments describe CLE as a "transport-only extension point" today, not a required upstream. This is an architectural promotion of CLE's importance that deserves an explicit decision, not an implicit one made by choosing this design.
  - If grounding fails and a fallback to raw text is added to cope, then *which* text produced a given position becomes non-deterministic from the outside unless meticulously logged per-event — reintroducing exactly the kind of ambiguity the task brief's "Do Not Fabricate" principle warns against.
- **Recommendation**: **not recommended for this vertical slice.** Named here because the task brief asked for at least 3 candidates and explicitly asked this exact risk to be surfaced.

### C. Attributes-only enrichment (hybrid of A, folded into the existing NVS request)

Same call-order change as A, but instead of a separate correlation channel, thread `GroundedState`'s fields (five_w1h values, sok, grounding-time `concept_id`/`normalized_hash`) into `ObservationEvent.attributes: dict[str, str]` — a field NVS's wire contract already declares and already accepts (`kernel_gateway.py`'s existing `_string_attributes()` helper already JSON-coerces non-string values into this exact shape for other purposes). NVS's `text` field, and therefore its computed position, remains unchanged — only the accompanying `attributes` dict grows richer.

- **What it achieves**: no new correlation/storage mechanism needed; the enrichment rides along on the same request/response cycle NVS already processes.
- **What is unverified**: whether nvs-kernel actually **persists or exposes** arbitrary `attributes` beyond ingesting them into its internal `ObservationEvent`/HEXT record was **not read this session** (nvs-kernel's `observation/models.py` and `hext/models.py` were not opened). If attributes are accepted but silently discarded downstream, this design provides no lasting value beyond A's wall-clock-ordering benefit. **UNVERIFIED — flagged as an open question (§15), not assumed either way.**
- **Risk**: unscoped attribute growth (arbitrary JSON blobs riding on every event) if not size-capped; NVS's `EventPayload.attributes` has no documented size limit read this session.

---

## 7. Recommended Design

**Design A (grounding-as-parallel-audit-capture), with Design C's attribute-enrichment as an explicitly deferred, separately-gated follow-on once nvs-kernel's `attributes` persistence is confirmed.**

**Why:**
- It is the only one of the three that does not require deciding, this round, whether CLE becomes a hard dependency of NVS's core measurement — a decision the task brief explicitly reserved by saying NVS must not be touched.
- It directly satisfies the audit's own "first fix" recommendation — establishing real call-order (`ground` before `observe`) with a working, tested `/ground` client — without smuggling in a semantic claim ("NVS is now grounded") that the current wire contract cannot actually support.
- It has the cleanest safety story for the "silent fallback" risk the brief called out: because NVS's input never depends on whether grounding succeeded, a grounding failure literally cannot change what is being measured. Design B could not make the same claim.
- It is fully reversible and independently toggleable (§13).

**What changes:** `sensos` only — a new `CLEClient.ground()` method, and one new call site in `ForwardWorker`, both additive.

**What does not change:** `categorical-lift-engine` (0 lines — `/ground` already exists, routed, tested), `nvs-kernel` (0 lines — text-only wire contract untouched), `hekb` (0 schema change this round).

**How V1 is protected:** the existing NVS→CLE(`/lift`)→HEKB chain (`_propagate_semantic_mapping`) is completely unmodified. The new grounding call is a sibling addition, not a replacement, and — per §10 — its failure must be observable (not silently swallowed the way `_propagate_semantic_mapping`'s failures are today) precisely because the task brief flagged that pattern as risky for a grounding step specifically.

**How this connects to 38 Ports later:** because Design A changes nothing about `session_id`, `event_id`, `sequence_id`, or `cycle` — the identity/provenance fields a future 38-Port integration would need to correlate observations — none of that surface is disturbed. A future port-invocation step could key off the same `event_id`/`session_id` this design already threads through the grounding call, without any rework.

---

## 8. Exact Files to Modify

All in `sensos` (`/Users/tomonam3/GemminAI/sensos/services/nvs-runtime/runtime/`):

| File | Change |
|---|---|
| `gateway/cle_client.py` | Add `CLEClient.ground(prompt: str, goal: str, *, five_w1h_overrides: dict \| None = None, embedding_dimension: int = 8) -> dict[str, Any]` — mirrors the existing `lift()` method's shape (plain dict wire mapping, `POST /ground`, reuses `self.call()`). No change to the existing `lift()` method. |
| `services/forward_worker.py` | New method `ForwardWorker._propagate_grounding(session_id: str, event_id: UUID, observation_event: ObservationEvent) -> None` (name illustrative, not final), called from `drain_once()` **before** `self.gateway.observe_batch(...)` — additive, does not alter the existing `_propagate_semantic_mapping()` call or its position in the flow. Constructor gains an optional flag/dependency for the feature toggle (§13). |
| `core/config.py` | New `Settings.enable_cle_grounding: bool = False` (default OFF — see §13 rollback plan). No change to existing `cle_url`/`hekb_url`/`nvs_kernel_url` fields. |
| `services/event_service.py` | **No change anticipated** under Design A — grounding stays in the async `ForwardWorker` path, consistent with the existing EXP-Ubuntu011 principle of keeping `ingest()`'s synchronous request path free of outbound calls (`event_service.py:59-65`'s own comment). Listed here only to record that it was considered and rejected as the call site. |
| `runtime/tests/test_forward_worker.py` | New tests mirroring the existing `_FakeCLE`/`_FakeGateway` pattern (§12). |
| `runtime/tests/test_extension_point_clients.py` | New unit test(s) for `CLEClient.ground()`'s wire mapping — this file already exists and, per its name, is the established location for exactly this kind of test; **not opened this session, so its current contents/conventions are UNVERIFIED** — read it before writing new tests here. |

Not modified: anything in `categorical-lift-engine`, `nvs-kernel`, or `hekb`.

---

## 9. Data Contract

`CLEClient.ground()` request mapping — candidates for each ambiguous field, since more than one exists:

| `GroundRequest` field | Candidate source | Basis | Problem |
|---|---|---|---|
| `prompt` | `envelope["payload"]["text"]` (the same text NVS receives) | Direct, obvious, matches "raw narrative" in the task's own framing | None significant — this is the one unambiguous mapping |
| `goal` (required) | (a) `""` (empty string) | Simplest; matches "no goal concept exists today" | `five_w1h.what` derives from `goal` (`five_w1h.py:85`) — empty goal ⇒ `what` is always `"unspecified"`, degrading grounding quality for every event |
| | (b) `str(envelope["event_type"])` (e.g. `"state.raw"`) | Something non-empty, cheap, already present | Semantically not a "goal" — a category label repurposed; could make `what` misleadingly look "derived" when it is actually just the event type string |
| | (c) New optional field on `EventIngestRequest` (e.g. `intent: str \| None`), defaulting to `""` if the caller doesn't supply one | Correct long-term shape; lets real callers who *do* have a goal express it | Requires a schema addition to `EventIngestRequest` — technically a "change" beyond the minimal file list in §8; **not decided here** — this is a product decision, listed as Open Question §15.2 |
| `five_w1h_overrides` | `{}` (all `None`, use derived-only) | Simplest; matches "don't invent semantics" instruction in the task brief | None derived from `who` today (no rule for `who` at all in `five_w1h.py:90` — `who=_field(overrides.who, None)` always falls through to `"unspecified"` unless explicitly overridden). **UNVERIFIED whether this is intentional in CLE or an oversight** — not CLE's code to change this round regardless |
| `default_knowledge_reference` | `"unspecified"` (CLE's own default) | No reason to override | None |
| `embedding_dimension` | `8` (CLE's own default) | No reason to override; this dimension only affects the grounding-time lift result (§3), not anything NVS-facing | UNVERIFIED whether any downstream consumer will eventually want a specific dimension |

`GroundResponse` → correlation/storage mapping (Design A): **UNVERIFIED / not decided in this plan** — the audit brief explicitly instructed not to decide HEKB schema changes this round (§8 of the task brief: "HEKB schemaにGroundedStateを保存する必要があるかどうかは、まだ決めない"). Two non-committal options for *where the response goes* in the interim, both deferring the HEKB-schema question:

1. Structured log line only (`logger.info(..., extra={"event_id":..., "session_id":..., "cle_ground_concept_id":..., ...})`) — zero persistence footprint, satisfies §11's observability requirement minimally, defers all storage decisions.
2. In-process return value discarded after logging (i.e., call `/ground`, log outcome + key fields, do not store the full `GroundedState` anywhere yet) — same effect as (1), stated separately because it's the literal "do the call, prove it works, decide storage later" reading of the task's Vertical Slice framing.

Both are compatible with "HEKB not touched this round." A dedicated HEKB object kind for grounding provenance is a natural next step but is explicitly **out of scope** here, per the task's own §8 instruction.

---

## 10. Error Semantics

Current established pattern (`forward_worker.py:171-181`, the CLE/HEKB "Semantic Mapping" leg): catch `_TRANSPORT_ERRORS`, log a warning, do not raise, do not affect `ForwardStatus`. The task brief explicitly warns this "silent fallback" pattern is dangerous for a grounding step, because whether grounding happened could affect what a measurement means.

Options, not pre-selected by this plan:

1. **Best-effort + explicit structured observability (recommended)**: same non-blocking behavior as the existing pattern (grounding failure must not block or affect the NVS forward — NVS's input never depended on grounding succeeding anyway, per Design A), **but** the failure must be logged with enough structure (`event_id`, `session_id`, error class, timestamp) to be queryable later, not just a free-text warning. This satisfies "don't silently lose information" without introducing a new hard dependency.
2. **Fail the whole event pipeline on grounding failure**: rejected. Would make the entire runtime's liveness depend on CLE's availability, contradicting `config.py`'s own framing of CLE as a "transport-only extension point," and violating the EXP-Ubuntu011 principle that already removed synchronous kernel RPC from the request path for exactly this class of reliability reason.
3. **Raw-text fallback on grounding failure**: under Design A this is not actually a distinct case — NVS always receives raw text regardless of grounding's outcome, so there is nothing to "fall back" to. This option only becomes meaningful under Design B, where it reintroduces the exact non-determinism-about-which-text-produced-which-geometry problem §6 already flags.
4. **Quarantine marking**: record a distinct status (not reusing `ForwardStatus.FORWARDED`, which must continue to mean only "NVS accepted this") — e.g. a separate, additive field or a structured log tag — so a failed/skipped grounding attempt is queryable without conflating it with NVS delivery success. Compatible with, and recommended in combination with, option 1.

**Recommendation: 1 + 4.** Not finalized as code — this is presented as the safest combination given the task's own stated concern, for the user to confirm before implementation.

---

## 11. Observability / Evidence

Minimum fields to record for every grounding attempt, regardless of outcome (mirroring the level of detail `ForwardWorker` already logs for the NVS/CLE/HEKB legs):

- `event_id`, `session_id`, `sequence_id` (already exist, threaded through unchanged)
- `cle_ground_request`: the `prompt`/`goal` actually sent (or a hash of them, if payload logging is a concern — **UNVERIFIED whether raw narrative text logging is acceptable under existing data-handling policy**, flagged as an open question)
- `cle_ground_response`: `concept_id`, `normalized_hash` (from the grounding-time `lift`), and the `five_w1h` values with their `source` tags (`explicit`/`derived`/`unspecified`) — cheap, useful, low-cardinality
- `outcome`: `success` / `failure` (with error class) / `skipped` (if gated by event type or feature flag)
- `timestamp` of the call and its duration (for future latency-budget tracking, given §14's latency risk)
- `cycle` (from the *existing* NVS response, for correlation with the same observation, once both calls have completed for a given event)

Whether this becomes a new DB table, a structured log sink, or both is **not decided here** (§9) — this section only fixes *what* must be captured, not *where*.

---

## 12. Test Plan

**Unit tests** (`runtime/tests/test_forward_worker.py`, mirroring the existing `_FakeGateway`/`_FakeCLE`/`_FakeHekb` pattern already used for `test_successful_forward_propagates_through_cle_to_hekb` and `test_semantic_mapping_failure_does_not_affect_nvs_forward_status`):
- New `_FakeCLE.ground()` method added to the existing fake.
- A grounding-success test, analogous in shape to the existing CLE/HEKB happy-path test, asserting: (a) `ground()` is called with the expected `prompt`, (b) the existing NVS `observe_batch()` call is unaffected (same text, same call count), (c) `ForwardStatus` remains `FORWARDED` regardless of grounding outcome.
- A grounding-failure test, analogous to `test_semantic_mapping_failure_does_not_affect_nvs_forward_status`, asserting the NVS leg is fully unaffected and the failure is observable per §10/§11's chosen mechanism.
- A feature-flag-off test, asserting `ground()` is never called when `Settings.enable_cle_grounding=False` (the default).

**Unit test for the wire client itself**: `runtime/tests/test_extension_point_clients.py` — this file already exists and, by its name, is the established home for exactly this kind of test (the existing `lift()`/`store()` wire-mapping tests presumably live here). **Not opened this session** — read its current contents and conventions before adding a `ground()` test, rather than assuming its shape.

**Integration test**: spin up `categorical-lift-engine`'s real FastAPI app (via `TestClient`, the same mechanism its own `tests/test_api_ground.py` already uses) and point a real (non-faked) `CLEClient` at it, verifying the full request/response round-trip against actual Pydantic validation on both sides — not just against hand-written fakes.

**Live smoke test**: `runtime/tests/test_kernel_gateway_live_e2e.py` already exists and, per its name, hits the real deployed GCP NVS endpoint under an env-var/marker gate. A new test in the same style (`test_cle_client_live_e2e.py` or similar) should hit the real deployed CLE `/ground` endpoint the same way — **this would also resolve Open Question §15.3** (whether `/ground` is live on the current GCP deployment) as a side effect of writing it. **Not written this session** — the existing live-e2e test's exact gating convention was not re-read; mirror it rather than inventing a new convention.

---

## 13. Rollback Plan

Design A is purely additive: one new client method, one new call site guarded by its own try/except, one new `Settings` flag, no changes to any existing method's signature or behavior, no schema changes anywhere. Two independent rollback mechanisms, both recommended together:

1. **Feature flag**: `Settings.enable_cle_grounding: bool = False` (default off). Turning grounding off requires no deploy — just an env var change — which is a materially faster rollback than a code revert.
2. **Git revert**: because the change is additive and touches no existing call sites' behavior when the flag is off, a plain revert of the implementing commit(s) is low-risk even without the flag, should the flag mechanism itself be judged insufficient.

No data migration is needed in either direction, since no schema changes are proposed this round.

---

## 14. Risks

1. **Latency added to the ForwardWorker background path.** Even non-blocking-on-failure, a slow (but eventually successful) CLE call still adds wall-clock time before the NVS call proceeds if grounding is placed strictly upstream of it (as recommended, for ordering). Mitigation: reuse the existing `NetworkProfile`-driven timeout/retry configuration `CLEClient` already has via `http_pool.py`, and confirm empirically (live smoke test, §12) before enabling by default.
2. **Two divergent "lift" results, unlabeled, could be conflated by a future reader.** Grounding-time lift (from CLE's own text-hash embedding) and post-NVS lift (from NVS's geometry) will generally disagree and measure different things. Mitigation: any storage/logging of either must carry an explicit, distinct label (e.g. `source: "cle_grounding"` vs `source: "nvs_semantic_mapping"`) — noted as a requirement for whichever storage mechanism is eventually chosen (§9 defers the mechanism, not this labeling requirement).
3. **`goal` mapping ambiguity (§9) risks systematically degraded grounding.** If `goal=""` is chosen by default, `five_w1h.what` will be `"unspecified"` for every single event, which may make the grounding-time lift result nearly content-free for that dimension. This is a real quality risk, not just a cosmetic one, and is a decision this plan explicitly does not make (§15.2).
4. **Attribute/log volume growth**, if grounding is attempted for every event without any filtering. Mitigation: consider gating by `RuntimeEventType` (mirroring `_FORWARDED_EVENT_KINDS`'s existing kind-filter pattern in `kernel_gateway.py:31-36`) — not decided here (§15.4).
5. **Naming-collision risk carried over from the audit.** Anyone implementing this must keep "CLE" = `categorical-lift-engine` unambiguous in code comments, commit messages, and variable names, given the confirmed existence of an unrelated same-named C++ repo (`sensos-cle`).
6. **CLE-side error semantics not fully characterized this session** (§3) — `CLEClient.ground()`'s exception handling is designed by analogy to `lift()`'s, but CLE's actual validation-error behavior (`cle.api.app`'s exception handlers) was not independently read.

---

## 15. Open Questions

1. Does nvs-kernel's `EventPayload.attributes: dict[str,str]` actually get persisted or exposed downstream (its `HextObject`/observation record), or only ingested and discarded? Not verified this session — determines whether Design C is worth pursuing later. (nvs-kernel's `observation/models.py`, `hext/models.py` not opened this round.)
2. What should `GroundRequest.goal` be, given `EventIngestRequest` has no "goal" concept today? Three candidates listed in §9 — this is a product decision, not resolved here.
3. Is `/ground` actually live on the current GCP deployment of `categorical-lift-engine` (`34.61.86.172:8000`)? The prior audit flagged this as unresolved; this plan's live smoke test (§12) would answer it as a byproduct, but no live probe was performed this session either.
4. Should grounding be attempted for every forwarded event, or gated to specific `RuntimeEventType`s (e.g. only `STATE_RAW`, mirroring the existing `_FORWARDED_EVENT_KINDS` filter)? Not decided.
5. Is `embedding_dimension=8` (CLE's own default) adequate for whatever eventually consumes the grounding-time lift result? No consumer exists yet, so this is unconstrained — flagged rather than guessed.
6. Is raw narrative text acceptable to log verbatim in the observability trail (§11), or does it need hashing/redaction under existing data-handling policy? Not checked this session — `sensos` has no data-handling policy document in scope for this audit.
7. `CLEClient.ground()`'s exact exception-translation behavior depends on reading `cle.api.app`'s exception handlers (§3, §14.6) — not done this session.
8. What does `runtime/tests/test_extension_point_clients.py` currently look like? Its existing conventions should shape the new `ground()` unit test rather than this plan inventing a new pattern — not opened this session.

---

## 16. Implementation Gate

Code must not be written until all of the following are explicitly resolved (by the user, or by a follow-up investigation session, not unilaterally by whoever picks this plan up):

1. §15.2 (`goal` mapping) — a decision, not a default, since the "simplest" option (empty string) has a disclosed quality cost (§14.3).
2. §15.4 (event-type gating scope) — resolved, or explicitly accepted as "all forwarded event types" with the volume risk (§14.4) accepted.
3. §10's error-semantics combination (recommended: 1 + 4) — confirmed, since this directly answers the task brief's own "silent fallback is dangerous" concern.
4. §13's feature-flag design (name, default, env var binding) — agreed.
5. Call site confirmed as `ForwardWorker` (background path), not `EventService` (synchronous request path) — consistent with the existing EXP-Ubuntu011 principle; stated as the recommendation in §8, needs explicit sign-off.
6. §12's test plan — specifically, `test_extension_point_clients.py` (§15.8) and the existing live-e2e test's gating convention (§12) should be read **before** writing new tests, not assumed.
7. **Explicit, written acknowledgment that this vertical slice does not make NVS's computed geometry depend on CLE's grounding** (§4, §7) — this is Design A's core honest limitation, not a hidden one, and the user should confirm this is an acceptable "V2 Step 1" before implementation proceeds, with any move toward Design B (or a future NVS-side schema change enabling real vector input) tracked as a separate, later, explicitly-scoped decision.

Until all seven are checked off, this remains a design document only.

```
[END OF PLAN: SENSOS-RTV2-PLAN-001]
```
