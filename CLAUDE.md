# SensOS Runtime Development Context

This document is working context for AI assistance in this repository. It is
**not** an architecture authority. Where anything below conflicts with
`docs/spec/PRODUCT_BOUNDARY.md` or `docs/spec/GIT_GOVERNANCE.md`, those
documents prevail, not this one.

## Cross-Repository Context (OKF) — read before assuming names refer to this repo alone

Before treating any of CLE / MSR / HEKB / MeaningMapper as referring to a
single implementation, read the OKF entry node:
`~/vaults/20260124/OKF/SensOS-Primer.md`. These acronyms each name multiple,
independent implementations across the SensOS repository family — see
`~/vaults/20260124/OKF/SensOS-Naming-Collisions.md` before writing code that
assumes which one is meant. This repository (`GemminAI/sensos`, `main`
branch) is the canonical one for SensOS development — see
`~/vaults/20260124/OKF/SensOS-Work-Rules.md`. `Projects/sensos` (`empty`
branch) is a separate, non-canonical checkout; do not treat work found there
as authoritative for this repository without review.

## Current Authority

- `docs/spec/PRODUCT_BOUNDARY.md` (v2.0.0, Status: Active) — sole boundary
  definition for this repository.
- `docs/spec/GIT_GOVERNANCE.md` (v1.0.0, Status: Active) — subordinate
  operating contract for branches/tags/releases; must not contradict
  `PRODUCT_BOUNDARY.md`.

Both are committed and unmodified by this file. This file does not add,
override, or reinterpret their authority.

## Evidence Promotion Rule

No claim about this system may be treated as implemented, connected, or
verified above the evidence tier that actually supports it:

```
SPEC → CODE → CONFIG → LIVE ENDPOINT → WIRE TRACE → TCK
```

A claim reaches `VERIFIED` only at `WIRE TRACE` or `TCK` tier — an actual
value traced from a real producer to a real consumer, or a live endpoint
response actually observed. A diagram, a proposal document, or a docstring
is `SPEC` tier only, regardless of how confidently it's written.

## V1 Baseline

Facts below reflect what a code/live-evidence audit of this repository
actually confirmed (external audit, not committed here — see "Open
references" at the end of this file). Treat as evidence, not as this file's
own authority.

- No git tag for "v1.0" exists in this repository. "v1.0" is a
  documentation-only Release Candidate label
  (`RELEASE_MANIFEST.md`: *"Candidate — not yet tagged"*).
- The one real, wire-traced data chain found in this repository:
  `NVS-Kernel POST /observe → response.geometry.position → CLE POST /lift(position) → HEKB store`.
  One-shot, one direction, terminates at HEKB.
- NVS-Kernel is real and live, with a real 8-layer pipeline (`L0`–`L7`).
  `L0` (Multi-modal Ingest) and `L7` (Policy Execution) are confirmed
  `NOT_IMPLEMENTED` on the live service as of the last check.
- CLE (Categorical Lift Engine) is real and live, with confirmed endpoints
  `/health /lift /pullback /recover /compress`. A `/ground` route exists in
  CLE's own source code but was confirmed **not exposed** on the live
  deployment as of the last check.
- 38 individually-addressable Core-wrapped Ports exist and are live
  (`POST /ports/{id}_Port/invoke`), separate from the `L0`–`L7` listing. All
  38 return real, observation-only responses in captured evidence — no
  intervention-shaped fields found in any of them.
- A DAK implementation exists as real code
  (`services/observation-runtime/sensos/dak/`,
  `TrajectoryDifferentialSafetyKernel`) — a linear risk score from three
  metrics, not a phase/thermostat controller. No downstream consumer of its
  decisions was found.
- Real LLM-generation capability exists in the broader ecosystem, but no
  binding to this repository's NVS/CLE/Port/DAK/HEKB pipeline was confirmed.

Anything not listed above should be treated as `UNKNOWN`, not assumed absent
or present.

## V2 Status

**V2 is PROPOSED / UNDER VALIDATION.** It describes a candidate
architecture to be evaluated, not what this repository currently
implements. No part of V2 may be treated as an implementation fact until it
is promoted through the Evidence Promotion Rule above.

`docs/spec/SPEC-SENSOS-RTV2-JSON-002.md` exists in this repository's working
tree as a draft (uncommitted as of the last check) describing a candidate
wire protocol. It is not named by `PRODUCT_BOUNDARY.md` or
`GIT_GOVERNANCE.md`. Several of its concrete claims — JCS/RFC 8785 actually
implemented in code, `/v2/*` endpoints existing, Port intervention
capability — were checked against live/wire evidence and found
**contradicted**, not merely unverified. Treat it as an input to V2
validation work, not as an active specification, and do not treat its
existence in this repository as making it Active.

`docs/SENSOS_KNOWLEDGE_CORE_AND_CATEGORY_THEORY.md` also exists in this
repository (uncommitted as of the last check). Its content has not been
verified against implementation and its authority status is `UNKNOWN`.

## Candidate V2 Path

```
CLE → NVS-Kernel → GPT-OSS → 38 Ports → DAK → HEKB
```

This is the path to be validated, not a description of a working system.
Per-edge status as last confirmed — do not upgrade any entry below without a
wire trace or live-endpoint observation supporting it:

| Edge | Status | Note |
|---|---|---|
| CLE → NVS-Kernel | **UNVERIFIED** (contradicted as stated) | No code path found in this direction; the confirmed real direction is the reverse (NVS-Kernel → CLE) |
| NVS-Kernel → GPT-OSS | **UNVERIFIED** | No session/state binding found between NVS-Kernel and any GPT-OSS (or other model) process |
| GPT-OSS → 38 Ports | **UNVERIFIED** | No code path found |
| 38 Ports → DAK | **UNVERIFIED** | DAK's real implementation consumes only hand-constructed test metrics, never live Port output |
| DAK → HEKB | **UNVERIFIED** | No code path found |
| NVS-Kernel → CLE → HEKB | **VERIFIED** | The one real edge in this list; wire-traced end to end |
| HEKB → next runtime cycle (feedback) | **UNVERIFIED / ABSENT** | No read-back method exists on the current HEKB client |

## 38-Port Policy

38 Ports are not reduced at this time. No N-Port compression target
(including any prior 8-Port proposal) is assumed as a design goal. Each
Port's real capability — name, stateless/session-scoped classification, and
whether it does anything beyond observation — is defined only from measured,
wire-level evidence, not assumed from a proposed taxonomy.

Note: a proposed cognitive-linguistic Port taxonomy (grouping Ports by
categories such as "Sub-Lexical," "Temporal," "Norm/Boundary") has been
checked against real captured Port capability names and does not match —
real names are topology/dynamical-systems terms (e.g.
`core_c17_spectral_topology_analyzer`). Do not assume that or any other
taxonomy without re-verifying against current live evidence.

## Development Rules

- Confirm current code before implementing anything new.
- Confirm API contracts against the live endpoint, not against a spec
  document alone.
- Obtain an actual wire trace (a real value traced from producer to
  consumer) before claiming two components are connected.
- Verify via TCK before claiming something production-ready. No `TCK-v1` or
  `TCK-v2` artifact currently exists anywhere in this repository under
  either name — do not assume one exists.
- Never promote a guess, a diagram, or a docstring claim to an
  implementation fact. If evidence is insufficient, mark it `UNKNOWN` or
  `UNVERIFIED` and say so, rather than filling the gap with plausible detail.
- Do not fabricate: for components with no real data, model, or endpoint,
  report `BLOCKED` or `NOT_EVALUABLE` rather than mocking a pass.

## Open References

- The V1/V2 gap audit and documentation governance audit that inform the
  "V1 Baseline" and "V2 Status" sections above were produced in a separate
  repository (`Projects/sensos/experiments/`), not committed to this one.
  This file does not assume that location is stable or authoritative for
  this repository — treat it as external evidence to re-verify, not as a
  citation this repository can rely on.
- Prior versions of this file referenced `sensos/specs/SPEC-SENSOS-RTV2-PHASED-ROADMAP-003.md`,
  `SensOS_v2_JSON_Contracts_Specification.md`, and
  `SensOS_Runtime_v2_Integration_Contract.md`. None of these exist anywhere
  in this repository as of the last check. They are not referenced above.
