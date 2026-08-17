# ADR-0014: GPT-OSS as a Semantic Anchor Provider (new capability, not an NVS-Kernel integration)

| Field | Value |
|-------|-------|
| Status | Accepted |
| Date | 2026-08-18 |
| Constitution | `docs/spec/PRODUCT_BOUNDARY.md`; builds on ADR-0013 |
| Related | `docs/audit/MCP_COMPLIANCE_AUDIT_20260818.md`, `experiments/SENSOS_RUNTIME_V2_CROSS_REPOSITORY_ARCHITECTURE_AUDIT.md` §10 |

## Reality Audit

Before any design work, this cycle re-confirmed what a prior audit had
already found: **no repository in this system contains a working GPT-OSS
integration.**

- `CLAUDE.md`'s own architecture table marks every GPT-OSS edge
  (`NVS-Kernel → GPT-OSS`, `GPT-OSS → 38 Ports`) **UNVERIFIED**: "No
  session/state binding found."
- `experiments/SENSOS_RUNTIME_V2_CROSS_REPOSITORY_ARCHITECTURE_AUDIT.md`
  §10: "No repository in this 13-repo audit contains a working GPT-OSS
  integration" — zero code hits for `gpt-oss`/`gptoss`/`gpt_oss` anywhere,
  only documentation mentions.
- `services/observation-runtime/sensos/evidence.py` and
  `replay_comparison.py`: both explicitly schema-only, "there is no
  GPT-OSS/EOU data to build one from yet."
- This cycle's own local-environment check: no MLX/mlx-lm, vLLM, or
  llama.cpp installed; Ollama was installed and running, but its only
  pulled model was `qwen2.5:0.5b` — not GPT-OSS.

**Consequence:** connecting GPT-OSS was not a wiring task ("find the
existing client and point it somewhere"). It required acquiring a real
model and writing a new connector from nothing. `gpt-oss:20b` (13GB) was
pulled via Ollama — the only inference runtime this host actually has —
and used for every live test in this cycle; nothing here is mocked or
relabeled from a different model.

## Decision

### 1. Capability boundary, not a Kernel embedding

```
GPT-OSS
  |  Semantic Anchor Provider  (runtime/services/semantic_anchor.py,
  v                             runtime/gateway/ollama_client.py)
SensOS Runtime
  v
Meaning Triangulation
```

GPT-OSS is wired as a new Runtime capability
(`request_semantic_anchor_triangulation()` in `capability_decision.py`,
the same Runtime Decision Boundary pattern `request_capability()` and
`request_meaning_trajectory()` already use), never embedded directly into
`KernelGateway` or any NVS-Kernel code path. NVS-Kernel is not touched by
this ADR.

### 2. `SemanticAnchor` — a new schema, deliberately not a resolution of the existing attestation ambiguity

`sensos.evidence`'s own module docstring documents an **unresolved**
tension between two different, non-identical attestation shapes already
in SPEC-SENSOS-RTV2-001 v1.4 (Contract 1's `dense_projection.attestation`:
7 fields; TCK-v2's G0-A replay-equality tuple: an overlapping but
different 7). Materializing either shape here would mean silently
resolving that flagged open question, which is out of this ADR's scope.

`SemanticAnchor` (`runtime/services/semantic_anchor.py`) is therefore a
**new** dataclass, reusing the *vocabulary* both existing shapes already
share (`model_id`, `model_revision`, `runtime`, sampling-parameter-style
reproducibility fields) so it does not introduce a third naming
convention, without claiming to unify anything:

```
anchor_id            content-addressed: sha256(model_id|model_revision|input_hash|prompt_version|response)
model_id             e.g. "gpt-oss:20b"
model_revision       Ollama's own content digest (GET /api/tags), not a hand-typed version string
runtime              "ollama" — which inference runtime actually served this
input_hash           sha256 of the observation text
prompt_version       key into PROMPT_TEMPLATES (versioned, never silently edited in place)
structured_result    {"summary": <the model's real, unmodified response text>}
provenance           {source_observation_id, generated_at}
reproducibility      {temperature, seed, done_reason, eval_count, total_duration_ns}
```

### 3. Determinism — only what was empirically verified is claimed fixed

Verified live against this host's Ollama before writing any client code:
identical `(model, prompt, temperature=0, seed=42)` produces byte-identical
`response` text across independent calls. Only `temperature` and `seed`
are set by `OllamaClient.generate()`. No claim is made about "reasoning
effort" or any other gpt-oss-specific sampling parameter, because none
other was verified controllable through this runtime.

GPT-OSS is never ground truth: `request_semantic_anchor_triangulation()`
builds the anchor's generated text into one Meaning Triangulation path
(`semantic_anchor_to_triangulation_input()`) and a **second**, independent
path directly from the raw observation text, then calls the existing,
unmodified `request_meaning_triangulation()` to compare them — the same
STABLE/DIVERGENT/NOT_EVALUABLE vocabulary, the same "no default distance
threshold" rule (Phase 2, previous cycle) applies to both paths equally.

### 4. HEKB — one backend (ADR-0013), full lineage as real graph edges

Every artifact — the SemanticAnchor object, both paths' trajectories, and
the triangulation summary — persists to the same hekbd instance (ADR-0013)
with real `DERIVES` morphisms, not only JSON labels:

```
SemanticAnchor --DERIVES--> anchor path's Trajectory --DERIVES--> Triangulation summary
                              direct path's Trajectory --DERIVES--/
```

`evidence_status` is `PERSISTED` only if every one of those writes
succeeds — reusing `request_meaning_triangulation()`'s own
all-or-`BLOCKED` contract for its half of the graph, plus one more
BLOCKED-capable step (the anchor's own store + relate) added by this ADR.

### 5. MCP is the interoperability layer, not the decision-maker

`nvs_request_semantic_anchor_triangulation` (MCP tool) is a thin wrapper
over `request_semantic_anchor_triangulation()` — it does not decide
anything a client couldn't decide by calling the Boundary function
directly. Discovery/decision/invocation live in
`runtime.services.capability_decision`, matching every other capability
in this Runtime; MCP only transports the request/response.

## Governance constraints honored (explicit, not implicit)

- GPT-OSS is not ground truth anywhere in this code — triangulation
  compares it, never substitutes it for the direct path.
- No code touches `KernelGateway` or any NVS-Kernel route.
- No session/state binding between NVS-Kernel and GPT-OSS is assumed or
  fabricated — this capability is entirely independent of NVS-Kernel.
- No fake GPT-OSS response and no fake HEKB persistence exist in any test
  in this cycle — live tests skip (do not fabricate success) when Ollama
  or hekbd is unreachable.
- No triangulation "correctness" score or undocumented threshold is
  introduced — `divergence_epsilon` remains caller-supplied (Phase 2,
  previous cycle), unchanged by this ADR.
- MeaningMapper's real chain is called unmodified.

## Alternatives considered

- **Embed GPT-OSS calls directly in NVS-Kernel / KernelGateway.** Rejected
  — explicitly prohibited by this cycle's own instructions, and would
  conflate a Runtime-owned capability with the Kernel's control-plane
  role (the same separation `docs/NVS-Kernel.md`, referenced in the prior
  HEKB audit, already draws between HEKB storage and NVS-Kernel judgment).
- **Reuse `sensos.evidence`'s attestation shape for SemanticAnchor.**
  Rejected — that shape's own docstring flags it as unresolved between two
  incompatible variants; forcing a third use case into either would compound
  the ambiguity rather than sidestep it.
- **Treat GPT-OSS output as the triangulation's reference/ground truth.**
  Rejected — explicitly prohibited; a Semantic Anchor is one more
  measurement, not an oracle.
