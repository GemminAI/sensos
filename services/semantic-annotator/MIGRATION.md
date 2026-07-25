# Migrating from `tag-generator` to `semantic-annotator`

## 1. Where each service lives

- **Old**: `tag-generator`, source lives in `~/nvs-platform` (RC1 Track A).
- **New**: `semantic-annotator`, source lives here, in `nvs-platform-runtime`
  (RC1 Track B).

These are two different repositories in a two-track RC1 split. This is a
new implementation in a new location, not an in-place upgrade.

## 2. Breaking response-shape change

Old `POST /annotate` returned a flat shape:

```json
{"T09": [...], "T10": 0.85, "T19": 0.15, "provider": "anthropic", "model": "...", "version": "v1", "tag_quality": {...}, "_signature": "ai:T33"}
```

New `POST /annotate` returns a nested `Annotation` envelope:

```json
{"version": "1.0", "tags": {...}, "subject": {...}, "entities": [...], "events": [...], "time": {...}, "location": {...}, "reference": null, "interpreter": null, "metadata": {...}, "confidence": {...}}
```

Old tags now live at `response.tags.T09_strategic_interest_vector`,
`response.tags.T10_epistemic_confidence`, `response.tags.T19_conflict_factuality_index`
- not top-level `T09`/`T10`/`T19`. There is no top-level `_signature` field
at all (see §6). `tag_quality` is replaced by `response.confidence.tags`,
keyed the same way but with a `{value, quality, reason}` shape instead of
`{value, provenance, quality}`.

Any caller of the old `/annotate` contract must be updated to read the new
shape - these are not wire-compatible.

## 3. Environment variable renames

| Old | New |
|---|---|
| `TAG_GENERATOR_HOST` | `SEMANTIC_ANNOTATOR_HOST` |
| `TAG_GENERATOR_PORT` | `SEMANTIC_ANNOTATOR_PORT` |
| `TAG_GENERATOR_TIMEOUT` | `SEMANTIC_ANNOTATOR_TIMEOUT` |
| default port `8010` | default port `8011` |

`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`GEMINI_API_KEY` and the
`*_MODEL` variables are unchanged.

## 4. Module/class renames

| Old (`~/nvs-platform/tag-generator/`) | New (`semantic-annotator/`) |
|---|---|
| `app/models.py` (`SYSTEM_PROMPT`, `TagResult`, `parse_annotation`) | split into `app/tags.py` (prompt + tags parsing) and `app/schemas.py` (`TagsBlock` pydantic model replaces `TagResult`) |
| `app/annotator.py` (`TagAnnotatorRegistry`, `annotate_text`) | `app/annotator.py::annotate_text` (registry hook dropped - unneeded, no `/annotate35` planned) |
| `app/config.py` (`Settings`) | folded into `app/annotator.py::Settings` |
| `app/tag_quality.py` + `app/signature_registry.py` | `common/confidence.py` (registry-lite; the full T01-T35 catalog and the RFC-HEXT006 `_signature`/`NARRATIVE_PARENT_SIGNATURE` coexistence machinery are dropped, see §6) |
| `providers/` (`BaseTagProvider`) | `backends/` (`BaseAnnotatorProvider`) - renamed because this service's responsibility is annotation, not "using an LLM"; a future rule-based/spaCy/GiNZA/CRF/BERT/local-model backend can implement the same interface |
| `schemas/tag_response.py`, `schemas/hext.py`, `schemas/health.py`, `schemas/coordinate_response.py` | `app/schemas.py` (single file; `hext.py`/`coordinate_response.py`'s content is not carried over, see §6) |

## 5. `runtime/services/tag_client.py` is NOT rewired by this change

`runtime/services/tag_client.py` in this repo still targets the old
`tag-generator` `/annotate` contract (`{"text","provider"}` in,
`{"T09","T10","T19","provider","model"}` out, with a local deterministic
fallback on any HTTP error). Wiring it to call `semantic-annotator` instead
is **out of scope for this change** - it's future CTG Engine integration
work per the CTG v7.0 architecture doc's cascade
(`Natural Language -> Semantic Annotator -> CTG Engine -> ...`). Whoever
does that wiring must handle the breaking response-shape change in §2.

## 6. What was intentionally dropped, and why

All of the following are measurement/geometry territory, or cross-repo
coupling this new service is explicitly designed to avoid - see README.md's
scope statement:

- `app/coordinator.py` (5D semantic coordinate projection `a_e/a_i/a_c/a_f/a_u`)
- `app/stream_engine.py` (HEXT Observation Stream enrichment, DAK-geometry input path)
- `POST /v2/enrich`, `POST /coordinate`, `POST /coordinate_batch`,
  `POST /trajectory`, `POST /pci`, `POST /phase28a` endpoints
- `NARRATIVE_PARENT_SIGNATURE` / `SignatureRegistry` / RFC-HEXT006
  coexistence machinery (the `_signature: "ai:T33"` field) - reintroducing
  this would recouple semantic-annotator to CTG/HEXT, which the new
  cascade architecture is specifically designed to decouple

If your integration depends on any of the above, it needs to talk to a
different, still-to-be-built service (the CTG Engine / Semantic
Measurement Framework), not semantic-annotator.
