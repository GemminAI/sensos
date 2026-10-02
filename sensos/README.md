# sensos

> **Current location:** this package currently lives inside
> `GemminAI/nvs-platform-runtime` (`sensos/`), on branch
> `feature/linux-sensos-installer`. It has not yet been integrated into
> `GemminAI/sensos` (currently a documentation-only repository) — see
> the migration report for how this maps onto it. Everything below
> describes this package as implemented today, in this location.

## 1. Status

- **Implemented.** The SensOS Linux Installer (`install.sh`) and the
  `sensos` CLI (`doctor`, `smoke`) exist and work.
- **Verified**: a fresh install was run end-to-end in a real Ubuntu
  24.04 Docker container (OS/Python/uv checks, `uv sync`, `uv pip
  install vllm`, `sensos doctor`).
- **Not yet verified**: end-to-end LLM inference (`sensos smoke`
  actually reaching a running vLLM server and producing an
  `AnnotatedObservation`) on a real Linux machine with an NVIDIA GPU.
  No such environment was available for this verification pass.

## 2. Quick Start

```bash
git clone https://github.com/GemminAI/sensos.git
cd sensos
./install.sh
```

This is the target flow once this package is integrated into
`GemminAI/sensos` (see the location note above). **Today**, from
inside this repository, the equivalent is:

```bash
git clone git@github.com:GemminAI/nvs-platform-runtime.git
cd nvs-platform-runtime/sensos
./install.sh
```

`sensos/pyproject.toml` depends on `semantic_annotator` via a relative
editable path (`../semantic_annotator`), so `sensos/` currently must
be run with `semantic_annotator/` present as a sibling directory, as it
is inside this monorepo. This is one of the open questions for the
`GemminAI/sensos` migration (see the report referenced above).

## 3. What the installer installs

`install.sh` installs:

- **SensOS Runtime** (the `sensos` package itself)
- **Semantic Annotator** (`semantic_annotator`, as an editable
  dependency)
- **vLLM** (`uv pip install vllm`)
- All of the above's required Python dependencies (via `uv sync` and
  `uv pip install`)

It does **not** start a vLLM server and does **not** download or pin
any model.

## 4. Python

Targets **Python 3.12** (`sensos/.python-version`,
`requires-python = ">=3.12"`, matching `semantic_annotator`'s own
requirement).

## 5. Commands

```bash
uv run sensos doctor
uv run sensos smoke
```

## 6. vLLM

- `install.sh` installs the **vLLM package** (`uv pip install vllm`).
- **Starting a vLLM server is separate from the installer.** `install.sh`
  never runs `vllm serve`; you start the server yourself:
  ```bash
  uv run vllm serve <model> --port 8000 --dtype auto
  ```
- SensOS consumes that server as a plain **OpenAI-compatible HTTP
  endpoint**, via `VLLMRuntimeBridge` and the `RUNTIME_BRIDGE_URL`
  environment variable — no tighter coupling than that.

## 7. Model

- The installer does **not** fix or download any specific model.
- The model is chosen by the user, at `sensos smoke` time, via
  `SENSOS_MODEL_ID` (or `--model`). There is no default.

## 8. Semantic Annotator path

```
SensOS
  → Semantic Annotator
    → RuntimeBridge
      → VLLMRuntimeBridge
        → vLLM
          → LLMAnnotator
            → AnnotatedObservation
```

`sensos` adds no annotation, transport, or inference logic of its own
— `RuntimeBridge` (Protocol), `CompletionResult`, `VLLMRuntimeBridge`,
and `LLMAnnotator` are all reused, unchanged, from `semantic_annotator`.

## 9. GPU / CUDA

- `sensos doctor` checks PyTorch import + `torch.cuda.is_available()`.
- In an environment with no CUDA GPU, this check **honestly reports
  FAIL** — it never fabricates a PASS.
- In this session's Docker verification (Docker Desktop on macOS, no
  GPU passthrough), the GPU check did FAIL. **This is not an installer
  failure** — it is the installer correctly reporting that the
  container it ran in has no GPU. Every other `doctor` check (OS,
  architecture, Python, uv, SensOS Runtime, Semantic Annotator, vLLM)
  PASSed in that same run.

## 10. Apple Silicon / MLX

**MLX is not integrated into this Linux installer, and is not planned
to be.**

`semantic_annotator.mlx_runtime_bridge.MLXRuntimeBridge` exists as an
independent, separate `RuntimeBridge` implementation inside
`semantic_annotator` for Apple Silicon (MLX/Metal) — it is unaffected
by anything in this package. MLX + GPT-OSS-20B
(`mlx-community/gpt-oss-20b-MXFP4-Q4`) has been verified end-to-end,
**PASS**, on real Apple M3 Pro hardware.

**No Apple Silicon installer is provided at this time** — only the
Linux installer described in this document exists today.

## 11. Verification status

| Item | Result |
|---|---|
| `sensos` test suite | **35 tests PASS** |
| `semantic_annotator` test suite | **45 tests PASS** |
| `integration` test suite | **27 tests PASS** |
| `ruff check .` (all three packages) | **PASS** |
| `mypy .` (all three packages) | **PASS** |
| Apple Silicon MLX + GPT-OSS-20B real-machine path | **PASS** |
| Linux Docker fresh install (`install.sh`, Ubuntu 24.04) | **PASS** |
| Linux NVIDIA GPU end-to-end inference | **NOT YET VERIFIED** |

## 12. Architecture

Linux and Apple Silicon are two separate, non-overlapping paths through
`semantic_annotator`. They share `RuntimeBridge`/`CompletionResult`/
`LLMAnnotator`, and nothing else.

**Linux** (this installer):
```
SensOS
  → Semantic Annotator
    → VLLMRuntimeBridge
      → vLLM
        → CUDA
```

**Apple Silicon** (not installer-integrated — see §10):
```
SensOS
  → Semantic Annotator
    → MLXRuntimeBridge
      → MLX / Metal
```

## Configuration

| Variable | Meaning | Default |
|---|---|---|
| `RUNTIME_BRIDGE_URL` | vLLM server's OpenAI-compatible base URL | none (required for `smoke`) |
| `SENSOS_MODEL_ID` | Model vLLM is serving | none (required for `smoke`) |

Same naming convention as `semantic_annotator/scripts/sa001_eval.py`'s
`RUNTIME_BRIDGE_URL` (that script's `GEMMA_MODEL_ID` was Gemma-specific;
`SENSOS_MODEL_ID` here is not).

## Reference

The vLLM/CUDA install steps this installer automates are the ones
actually executed and verified in
`docs/handoff/HANDOFF_SA001_RUNPOD_BASELINE.md` (`pip install vllm`;
`vllm serve <model> --port 8000 --dtype auto --gpu-memory-utilization
0.85 --max-model-len 4096`) — not invented. That document's own real
runs used `Qwen/Qwen2.5-0.5B-Instruct` and `google/gemma-4-E4B-it`;
GPT-OSS-20B has not been run through vLLM anywhere in this repository
(only through MLX, on macOS) — which is why no default model is assumed
here.
