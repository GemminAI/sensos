# SensOS Runtime v1.0.0 — Release Manifest

|Field|Value|
|---|---|
|Document|Release Manifest|
|Runtime|SensOS Runtime v1.0.0|
|Candidate|RC1|
|Status|**Candidate — not yet tagged**|
|Date|2026-08-07|
|Source Report|`SensOS_Runtime_v1_Integrated_Validation_Report.pdf` (EXP-HEKB001–007, EXP-Ubuntu010A–012)|
|Related|`docs/adr/ADR-0012-deployment-migration-to-distributed-runtime.md`|

## 1. Scope

This manifest records the exact commit, on `main`, that each component
repository contributes to SensOS Runtime v1.0.0 RC1. It is produced by a
**Release Candidate Integration** pass: safe local merges of already-diverged
branches into `main`, with no history rewrites, no force pushes, and no tags
created. See §4 for what remains before `runtime-v1.0.0` can be tagged.

## 2. Component Table (RC1)

| Repository | Role | RC1 Commit (`main`) | Merged From | Local `main` vs `origin/main` | Independent Version Line | Notes |
|---|---|---|---|---|---|---|
| `sensos` | Runtime orchestrator (Observation → NVS → CLE → HEKB) | `3693aeb` | — (direct commit) | ahead by 1 | unreleased (no prior tags) | ADR-0012 normalized and indexed in this commit |
| `hekb` | Hyper-Epistemic Knowledge Base | `3cb08c2` | `packaging/mcp-registry` (merge, 6 commits) | ahead by 3 (2 pre-existing + 1 merge) | last tag `v1.0.1` (2026-07-29) | In-progress API work (`api.py`, `api_storage.py`, `test_api.py`, `Dockerfile.api`, `docs/hekb-api.md`, `uv.lock`, compose/pyproject changes) intentionally **excluded** from RC1; preserved via `git stash` on `packaging/mcp-registry` |
| `nvs-kernel` | NVS-Kernel physics/observation engine | `ad99c97` | `feat/rfc-sensos16-v3-phase1` (merge, 22 commits incl. 1 docs commit) | ahead by 23 | last tag `v5.0.0` (2026-07-25) | 3 documentation files committed prior to merge: `docs/CANONICAL_RUNTIME_MAPPING.md`, `docs/SEMANTIC_PORT_GAP_REPORT.md`, `docs/SEMANTIC_PORT_L3_VALIDATION.md`. Stray `.DS_Store` files deleted (not part of history). |
| `categorical-lift-engine` (CLE) | Categorical Lift Engine | `74d8387` | `claude/cle-fastapi-service-phase1` (merge, 2 commits) | ahead by 3 | last tag `v0.1.0` | Working tree was clean; no exclusions |
| `hext` | HEXT object model / spec | `94c728a` | — (already on `main`) | in sync | last tag `v1.0.0` (2026-07-07, "HEXT Standard 1.0" — a **spec** release, unrelated to this Runtime release) | No changes made this pass |
| `meaning-mapper` | Meaning Mapper (RFC-SA / RFC-MSR) | `ee0f932` | — (already on `main`) | ahead by 2 (**not pushed**, pre-existing, unrelated to this pass) | last tag `v2.0.0` (2026-08-04) | No changes made this pass; 2 local commits predate this release effort |

## 3. Excluded From RC1

| Repository | Excluded Work | Where It Lives Now | Reason |
|---|---|---|---|
| `hekb` | HEKB HTTP API implementation (FastAPI-style `api.py`/`api_storage.py`, tests, `Dockerfile.api`, docs, lockfile, compose/pyproject config changes) | `git stash` on `packaging/mcp-registry` (restored to working tree, uncommitted) | Explicit release-scope decision: not confirmed ready to ship in Runtime v1.0.0 |

## 4. Outstanding Before `runtime-v1.0.0` Can Be Tagged

1. **hekb**: decide the fate of the stashed API work (ship in a later RC, or a separate hekb release) — currently untouched and unreleased.
2. **hext**: the existing `v1.0.0` tag is a *HEXT Standard* spec release, not a software release for this Runtime — confirm the naming scheme for a Runtime-wide tag does not collide with or overload it.
3. **meaning-mapper**: 2 local commits on `main` are still unpushed to `origin/main`, independent of this release pass — confirm whether they should be pushed before/alongside the release.
4. **All repos**: `runtime-v1.0.0` (or an equivalent cross-repo release identifier) has not been created anywhere. No `git tag`, `git push --tags`, tag moves, or force pushes have been performed as part of this manifest.
5. **All repos**: none of the local `main` branches above have been pushed to `origin` as part of this pass — RC1 exists only locally on this machine.

## 5. Non-Actions (By Design)

Per explicit instruction, this Release Candidate Integration pass did **not**:
- create, move, or delete any git tag
- run `git push` or `git push --tags`
- force-push or rewrite any history
- push any of the `main` branches updated above to `origin`
