# semantic-annotator

The observation interface of **SensOS**. It converts raw **Reality
Observations** into **Annotated Observations** by attaching semantic
labels, giving every downstream SensOS component a consistent,
interpreted view of what the system has observed.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker (optional, for containerized runs)

## Setup

```bash
uv sync
```

This creates a `.venv` and installs the project plus its dev
dependencies (ruff, mypy, pytest).

Install the git hooks once per clone:

```bash
uv run pre-commit install
```

## Usage

Read newline-delimited JSON `Observation`s from stdin and write
newline-delimited JSON `AnnotatedObservation`s to stdout:

```bash
echo '{"id": "obs-1", "source": "camera-1", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {"text": "a cat sat on the mat"}}' \
  | uv run semantic-annotator
```

Or via a file:

```bash
uv run semantic-annotator --input observations.ndjson --output annotated.ndjson
```

Or as a Python module:

```bash
uv run python -m semantic_annotator
```

## Development

```bash
uv run pytest              # tests
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy .              # type check
uv run pre-commit run --all-files
```

## Docker

```bash
docker build -t semantic-annotator .
docker run --rm -i semantic-annotator < observations.ndjson
```

## SA001: LLM-backed Annotator baseline (vLLM + RunPod)

`LLMAnnotator` (`src/semantic_annotator/llm_annotator.py`) is a real-inference
`Annotator` that talks to an OpenAI-compatible vLLM server through a
`RuntimeBridge` (`src/semantic_annotator/runtime_bridge.py`). It is not wired
into the default CLI (`main()` still hardcodes `PassthroughAnnotator` --
see `docs/ARCHITECTURE_REVIEW.md`); it is exercised via a dedicated
evaluation script, `scripts/sa001_eval.py`, per
[`../docs/handoff/HANDOFF_SA001_RUNPOD_BASELINE.md`](../docs/handoff/HANDOFF_SA001_RUNPOD_BASELINE.md)
(RFC-OBS000/RFC-EXP5100 and the SA001 handoff moved to the monorepo's
top-level `docs/` as of the 2026-07-18 repository consolidation --
they govern more than this one package).

```bash
cp .env.example .env   # fill in GEMMA_MODEL_ID and HF_TOKEN first

docker compose up -d
docker compose logs -f vllm   # wait for a clean startup, no traceback

docker compose exec semantic-annotator \
  python scripts/sa001_eval.py --samples scripts/sa001_samples.ndjson
```

The eval script reports JSON Validity, Schema Conformance, Determinism,
Latency, and Token Efficiency against the fixed sample set in
`scripts/sa001_samples.ndjson`, per the handoff's §7 evaluation battery.
`GEMMA_MODEL_ID` and the GPU tier in `docker-compose.yml` are still
placeholders as of this writing -- see the handoff's §8 (Known Risks)
before running against a real GPU.

## Project layout

```
src/semantic_annotator/   # library + CLI (src layout)
tests/                    # pytest suite, mirrors src/ package structure
scripts/sa001_eval.py     # SA001 evaluation harness (not part of the package)
docs/ARCHITECTURE.md      # architecture document
docs/ARCHITECTURE_REVIEW.md
.github/workflows/        # CI: lint, type check, test, docker build
```

RFC-OBS000, RFC-EXP5100, and the SA001 handoff live at the monorepo's
top-level `docs/rfc/` and `docs/handoff/` (see `nvs-platform-runtime`'s
own README) since they govern the contract between this package and
others in the repo, not just this package's own internals.
