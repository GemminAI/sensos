# Architecture

## Purpose

`semantic-annotator` is the **observation interface** of SensOS. SensOS's
Reality layer produces raw **Observations** — facts about the world as
captured by sensors and upstream systems, with no semantic
interpretation attached. Everything else in SensOS wants to reason
about *what those observations mean*, not just that they occurred.

`semantic-annotator` sits between the two: it consumes Observations and
produces **Annotated Observations**, attaching semantic labels
(classification, entities, taxonomy references, confidence) so that
downstream SensOS components share one interpreted, queryable view of
reality instead of each re-deriving meaning from raw payloads.

```
                 ┌────────────────────┐
 Reality  ─────▶ │  semantic-annotator │ ─────▶  Annotated Observations
 Observations    │  (this service)     │         (consumed by SensOS)
                 └────────────────────┘
```

## Design goals

- **Narrow, stable contract.** The only thing downstream consumers
  depend on is the `Observation → AnnotatedObservation` shape. How
  annotation happens internally can change freely.
- **Annotation strategy is swappable.** Keyword matching, embedding
  similarity, an LLM call, or a hybrid — all are implementations of the
  same `Annotator` interface, chosen at the edge (CLI/service wiring),
  not baked into the pipeline.
- **Streaming by default.** Observations are annotated one at a time
  via a generator pipeline, so the service doesn't need to hold a full
  batch in memory and can be run over unbounded streams.
- **No framework lock-in yet.** The initial architecture has zero
  runtime dependencies beyond the standard library, so the annotation
  strategy (rules, embeddings, an LLM) can be chosen deliberately later
  without unwinding an earlier choice.

## Module map

| Module | Responsibility |
| --- | --- |
| `semantic_annotator.models` | Domain types: `Observation`, `Annotation`, `AnnotatedObservation`. Immutable dataclasses — the shared vocabulary every other module depends on. |
| `semantic_annotator.annotator` | The `Annotator` protocol plus concrete implementations (`PassthroughAnnotator` as a no-op baseline, `KeywordAnnotator` as a minimal reference implementation). This is where future annotation strategies (embeddings, LLM-based, rule engines) plug in. |
| `semantic_annotator.pipeline` | Orchestration only: streams `Observation`s through an `Annotator` and yields `AnnotatedObservation`s. No I/O, no annotation logic. |
| `semantic_annotator.cli` | Adapter layer: parses NDJSON from stdin/file, drives the pipeline, serializes results back to NDJSON. Owns process framing, not domain logic. |

Dependency direction is one-way: `cli` → `pipeline` → `annotator` →
`models`. Nothing in `models` or `annotator` knows about the CLI or I/O
format, so the annotation core can be reused behind a different
transport (HTTP service, message queue consumer, batch job) without
change.

## Data contracts

**Observation** (input, produced by SensOS's Reality layer):

```python
Observation(
    id: str,
    source: str,
    timestamp: datetime,
    payload: dict[str, Any],
)
```

**AnnotatedObservation** (output, consumed by the rest of SensOS):

```python
AnnotatedObservation(
    observation: Observation,
    annotations: tuple[Annotation, ...],
    annotated_at: datetime,
    annotator_version: str,
)
```

Each `Annotation` carries a `label`, a `confidence` in `[0, 1]`, and an
optional `taxonomy` reference, so consumers can filter by confidence or
map labels back to a shared taxonomy without touching this service.

The wire format (NDJSON via the CLI) is an adapter detail, not part of
the domain contract — a future HTTP or queue-based transport would
serialize the same `models` types differently without changing
`pipeline` or `annotator`.

## Extension points

- **New annotation strategy**: implement `Annotator.annotate()` and
  wire it up wherever an `Annotator` is instantiated (currently
  `cli.main`). No changes needed to `pipeline` or `models`.
- **New transport**: add a module alongside `cli.py` (e.g. an HTTP
  handler) that parses input into `Observation`s and calls
  `run_pipeline`, mirroring what `cli.py` does for NDJSON.
- **Richer taxonomy validation**: currently `Annotation.taxonomy` is an
  unvalidated string reference; a taxonomy service integration would
  live in a new module, not inside `models`.

## Out of scope for this initial architecture

- Persistence of Observations or AnnotatedObservations (SensOS owns
  storage; this service is a pure, stateless transform).
- Authentication/authorization and multi-tenancy — deferred until this
  service has a network-facing transport.
- A production annotation model. `KeywordAnnotator` exists to prove the
  pipeline end-to-end, not as the intended long-term strategy.
