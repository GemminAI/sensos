# SensOS

## 1. Title / Status

**SensOS** is an Observation-Centered Intelligence platform: a small set
of independently-versioned components (a Semantic Annotator, an
inference `RuntimeBridge`, a Linux installer, and — separately — a
knowledge-storage library, HEKB) connected by narrow, explicit
contracts, rather than one monolithic runtime.

> **Where the implementation lives:** the code described below is in
> this repository: the SensOS Linux installer and `sensos` CLI are in
> `sensos/`, and the Semantic Annotator they depend on is in
> `semantic_annotator/`. They were migrated unchanged from
> `GemminAI/nvs-platform-runtime`, branch `feature/linux-sensos-installer`
> (commit `b21f75a`). Everything in this README was implemented and
> verified in that original location (§9); it has not yet been
> re-verified from this repository. This README describes that verified
> implementation accurately, including exactly what has and hasn't been
> checked.

Status, in one line per area (see §3 for the full table): the **Linux
installer, Semantic Annotator, and vLLM path are implemented and
fresh-install verified**; **Apple Silicon MLX inference is implemented
and real-hardware verified, but not installer-integrated**; **HEKB is a
separate, standalone library, Fresh-Install verified on its own, with
no SensOS integration implemented yet**; **MCP integration does not
exist**.

## 2. What is SensOS

SensOS observes the world, annotates what it observes, and (in later,
not-yet-implemented phases) is intended to store and reason over that
knowledge. Today, the implemented slice of that pipeline is:

```
Observation → Semantic Annotator → LLMAnnotator → RuntimeBridge → (vLLM or MLX) → AnnotatedObservation
```

`RuntimeBridge` is a Protocol with two independent implementations —
`VLLMRuntimeBridge` (Linux, vLLM/CUDA) and `MLXRuntimeBridge` (Apple
Silicon, MLX/Metal) — both feeding the same, unmodified `LLMAnnotator`.
Knowledge storage (HEKB) exists as a separate, standalone library (§8)
that nothing in this pipeline currently calls.

## 3. Current Status

| Component | Status |
|---|---|
| SensOS Runtime (`sensos` package: `doctor`, `smoke` CLI) | **Implemented, fresh-install verified** (Linux/Docker) |
| Semantic Annotator (`RuntimeBridge`, `LLMAnnotator`) | **Implemented, tested** (45 tests) |
| Linux Installer (`install.sh`) | **Implemented, fresh-install verified** (Ubuntu 24.04 Docker) |
| `VLLMRuntimeBridge` + vLLM | **Implemented, package installs and imports verified**; real inference against a running vLLM server on a CUDA GPU **not yet verified** |
| CUDA / NVIDIA GPU inference (end-to-end) | **Not yet verified** — no CUDA GPU environment was available for this verification pass |
| Apple Silicon / MLX (`MLXRuntimeBridge`) | **Implemented, real-hardware verified end-to-end** (Apple M3 Pro, GPT-OSS-20B); **not integrated into the Linux installer**, and no Apple Silicon installer exists |
| HEKB | **Standalone library, Fresh-Install verified on its own**; **not integrated with SensOS** — the Linux installer does not install it, and no code connects it to Semantic Annotator |
| MCP | **Not implemented** |

## 4. Quick Start — Linux

```bash
git clone https://github.com/GemminAI/sensos.git
cd sensos
./install.sh
```

`./install.sh` at the repository root runs `sensos/install.sh`
unchanged. The Python environment is created inside `sensos/`
(`sensos/.venv`), and `sensos/pyproject.toml` depends on
`semantic_annotator/` as a sibling directory (a relative editable
path), so keep both directories together. Run the commands in §5 and
§6 from `sensos/` (`cd sensos`).

`install.sh` installs the SensOS Runtime, Semantic Annotator, and vLLM
(`uv sync` + `uv pip install vllm`). It does **not** start a vLLM
server and does **not** download or assume any specific model.

## 5. `sensos doctor`

```bash
uv run sensos doctor
```

Checks OS, architecture, Python, uv, SensOS Runtime, Semantic
Annotator, vLLM, and CUDA/GPU availability — PASS/FAIL per item, never
loads a model. In an environment with no CUDA GPU, the GPU check
**honestly reports FAIL**; this is correct behavior, not an installer
defect (see §9).

## 6. `sensos smoke`

```bash
uv run vllm serve <model> --port 8000 --dtype auto
export RUNTIME_BRIDGE_URL=http://localhost:8000
export SENSOS_MODEL_ID=<model>
uv run sensos smoke
```

Runs one real `Observation` through `LLMAnnotator` → `VLLMRuntimeBridge`
→ vLLM → `AnnotatedObservation`. No model is assumed or downloaded by
default — you choose it. If the backend isn't configured or reachable,
`smoke` reports a real FAIL and which layer failed — never a fabricated
PASS.

## 7. Architecture

Linux and Apple Silicon are two separate, non-overlapping paths that
share only `RuntimeBridge` / `CompletionResult` / `LLMAnnotator`.

**Linux** (installer-integrated):
```
SensOS
  → Semantic Annotator
    → VLLMRuntimeBridge
      → vLLM
        → CUDA
```

**Apple Silicon** (implemented and real-hardware verified, but **not**
installer-integrated — no Apple Silicon installer exists):
```
SensOS
  → Semantic Annotator
    → MLXRuntimeBridge
      → MLX / Metal
```

## 8. HEKB

Canonical implementation: [`GemminAI/HEKB`](https://github.com/GemminAI/HEKB)
— a separate, standalone, storage-ignorant, category-theoretic
knowledge library. It has its own Fresh Install verification (clone,
`uv sync`, empty-state initialization, read/write, 29 tests — all PASS)
documented in its own README.

- Persistent storage backends (PostgreSQL, ScyllaDB, ...) are **not**
  part of the current HEKB package — only an in-memory backend, for
  tests/demos, ships today.
- **SensOS integration is not yet implemented.** No code in
  `semantic_annotator`, the SensOS Linux Installer, or this repository
  connects to HEKB. The SensOS installer does not install HEKB.
- HEKB can be installed and used entirely on its own (see its README),
  independent of SensOS.

## 9. Verification

Test suites (`nvs-platform-runtime`, branch `feature/linux-sensos-installer`):

| Suite | Result |
|---|---|
| `sensos` | **35 tests PASS** |
| `semantic_annotator` | **45 tests PASS** |
| `integration` | **27 tests PASS** |
| `ruff check .` (all three) | **PASS** |
| `mypy .` (all three) | **PASS** |

**Linux:**
- Ubuntu 24.04 Docker fresh install (`install.sh`, including `uv pip
  install vllm`): **PASS**
- `sensos doctor` in that container: every check **PASS** except
  GPU/CUDA, which correctly **FAIL**ed — that container has no GPU
  passthrough; this is the installer honestly reporting its
  environment, not a defect.
- Real inference against vLLM on a Linux NVIDIA GPU: **NOT YET
  VERIFIED**.

**Apple Silicon:**
- MLX 0.32.0 / mlx-lm 0.31.3 on Apple M3 Pro, `Device(gpu, 0)`: **PASS**
- `mlx-community/gpt-oss-20b-MXFP4-Q4` load + generation via
  `MLXRuntimeBridge`: **PASS**
- Harmony `final`-channel extraction (`harmony.py`): **PASS**
- Full chain `MLXRuntimeBridge → GPT-OSS-20B → Harmony extraction →
  LLMAnnotator → AnnotatedObservation`: **PASS**

**HEKB** (standalone, see §8): fresh clone → `uv sync` → empty-state
initialization → read/write test → 29 tests: **all PASS**.
**SensOS integration: NOT YET IMPLEMENTED.**

## 10. Current Limitations / Next Phase

Explicitly not yet done — none of the following should be read as
implemented:

- **Linux NVIDIA GPU end-to-end inference** — vLLM and CUDA install
  correctly; a real GPU has not yet run a real generation through this
  stack.
- **HEKB integration** — no code connects Semantic Annotator's
  `AnnotatedObservation` output to HEKB's `HEKBCoreRuntime`.
- **MCP integration** — does not exist in any form yet.
- **Apple Silicon installer** — `MLXRuntimeBridge` works and is
  real-hardware verified, but there is no installer for it; only the
  Linux installer exists.
- **A common CUDA/MLX inference abstraction above `RuntimeBridge`** —
  today, `VLLMRuntimeBridge` and `MLXRuntimeBridge` are two independent
  implementations of the same Protocol; there is no higher-level
  backend-selection layer.
