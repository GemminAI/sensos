"""GPT-OSS Semantic Anchor Provider.

    GPT-OSS
      |  Semantic Anchor Provider (this module)
      v
    SensOS Runtime
      v
    Meaning Triangulation

Reality Audit (2026-08-18, see docs/adr/ADR-0014-gpt-oss-semantic-anchor.md
for the full account): no repository in this system contained a working
GPT-OSS integration before this module — CLAUDE.md's own architecture
table marked every GPT-OSS edge UNVERIFIED, and an exhaustive grep found
zero connection code anywhere. Ollama was the only locally-installed
inference runtime (MLX/mlx-lm, vLLM, llama.cpp were checked and are
absent), so `gpt-oss:20b` was pulled through it — a real model, not a
placeholder or a different model relabeled.

`SemanticAnchor` is a NEW schema, not a reuse of `sensos.evidence`'s
attestation fields — that module's own docstring documents an unresolved
tension between two DIFFERENT, non-identical attestation shapes already in
the v1.4 spec (Contract 1's dense_projection.attestation vs. TCK-v2's G0-A
replay-equality tuple) and explicitly declines to pick one. This module
does not resolve that question either; it reuses the same *vocabulary*
those two shapes already share (model_id, model_revision, runtime,
sampling-parameter-style reproducibility fields) so a reader does not have
to learn a third naming convention, without claiming to unify anything.

GPT-OSS is never treated as ground truth here: this module only produces a
measurement (one more observation of a claimed meaning), for Meaning
Triangulation to compare against MeaningMapper/Trajectory's own
measurement of the same content — see
`semantic_anchor_to_triangulation_input()`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from runtime.gateway.ollama_client import OllamaClient
from runtime.services.meaning_trajectory import build_hext_observation
from runtime.services.meaning_triangulation import TriangulationInput

#: Versioned prompts. A new prompt is a new version, never a silent edit of
#: an existing one -- `prompt_version` is only a meaningful provenance
#: field if the text behind a given version never changes.
PROMPT_TEMPLATES: dict[str, str] = {
    "v1": (
        "Restate the following observation in one concise, literal sentence. "
        "Do not add information that is not present in the text.\n\n"
        "Observation: {text}"
    ),
}

#: The only sampling parameters this module fixes, because they are the
#: only ones empirically confirmed deterministic via this host's Ollama
#: (runtime.gateway.ollama_client's own docstring) -- reasoning effort /
#: other gpt-oss-specific knobs are NOT claimed fixed here unless verified.
DEFAULT_TEMPERATURE = 0.0
DEFAULT_SEED = 42


@dataclass(frozen=True)
class SemanticAnchor:
    """One real GPT-OSS (or whichever model_id) measurement of one
    observation's meaning. Not ground truth -- one more triangulation leg."""

    anchor_id: str
    model_id: str
    model_revision: str | None
    runtime: str
    input_hash: str
    prompt_version: str
    structured_result: dict[str, Any]
    provenance: dict[str, Any]
    reproducibility: dict[str, Any]


def _input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _anchor_id(model_id: str, model_revision: str | None, input_hash: str, prompt_version: str, response_text: str) -> str:
    """Content-addressed, matching HEKB's own convention: identical
    (model, revision, input, prompt version, output) always yields the
    same anchor_id."""
    canonical = f"{model_id}|{model_revision or ''}|{input_hash}|{prompt_version}|{response_text}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def request_semantic_anchor(
    observation_text: str,
    *,
    observation_id: str,
    model_id: str,
    prompt_version: str,
    client: OllamaClient,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int = DEFAULT_SEED,
) -> SemanticAnchor:
    """Runs one real generation against `client` and returns a SemanticAnchor.

    Raises whatever `client.generate()` raises on transport failure --
    same failure-propagation convention as the rest of this cycle's Runtime
    Decision Boundary functions (no fabricated anchor on a failed call).
    """
    if prompt_version not in PROMPT_TEMPLATES:
        raise ValueError(f"unknown prompt_version: {prompt_version!r}")
    prompt = PROMPT_TEMPLATES[prompt_version].format(text=observation_text)

    result = await client.generate(model_id, prompt, temperature=temperature, seed=seed)
    model_revision = await client.digest_of(model_id)

    response_text = str(result.get("response", ""))
    input_hash = _input_hash(observation_text)

    return SemanticAnchor(
        anchor_id=_anchor_id(model_id, model_revision, input_hash, prompt_version, response_text),
        model_id=model_id,
        model_revision=model_revision,
        runtime="ollama",
        input_hash=input_hash,
        prompt_version=prompt_version,
        structured_result={"summary": response_text},
        provenance={
            "source_observation_id": observation_id,
            "generated_at": datetime.now(UTC).isoformat(),
        },
        reproducibility={
            "temperature": temperature,
            "seed": seed,
            "done_reason": result.get("done_reason"),
            "eval_count": result.get("eval_count"),
            "total_duration_ns": result.get("total_duration"),
        },
    )


def semantic_anchor_to_triangulation_input(
    anchor: SemanticAnchor, *, path_id: str, base_time: datetime | None = None, count: int = 8
) -> TriangulationInput:
    """Turns a SemanticAnchor into a Meaning Triangulation path.

    The anchor's own generated text becomes the HEXT Observation body for
    this path, run through the SAME unmodified MeaningMapper -> MSR chain
    every other path uses (`run_meaning_trajectory`, invoked by
    `run_meaning_triangulation` itself -- this function only builds the
    input, it does not run anything).

    `count` real HEXT Observations are built from the SAME anchor text
    (default 8, matching this cycle's other triangulation paths and
    MSR's own dwell_steps=5 stabilization criterion) rather than one --
    a single observation cannot stabilize at all (a real MSR limit, not a
    choice of this module), and generating `count` independent completions
    would defeat the point of a *deterministic* anchor. Repeating one real,
    already-generated anchor `count` times is the "identical input replay"
    leg for this path specifically, not fabricated data: every repetition
    is the literal, unmodified text GPT-OSS actually produced.
    """
    start = base_time or datetime.now(UTC)
    observations = [
        build_hext_observation(
            observation_id=f"{path_id}-anchor-{i:04d}",
            text=anchor.structured_result["summary"],
            state_hash=anchor.anchor_id,
            sealed_at=(start + timedelta(seconds=i)).isoformat(),
        )
        for i in range(count)
    ]
    return TriangulationInput(path_id=path_id, observations=observations, method="gpt_oss_semantic_anchor")
