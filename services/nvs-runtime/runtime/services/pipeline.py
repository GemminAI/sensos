"""Narrative generation pipeline: Article → Narrative → Annotation → state_hash → PostgreSQL."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from runtime.providers.router import generate_narrative
from runtime.services.crystallizer import SCHEMA_VERSION, derive_event_id, compute_epistemic_diffusion_state, crystallize_state_hash
from runtime.services.semantic_annotator_client import SemanticAnnotatorClient
from runtime.services.state_service import StateService

NARRATIVE_PROMPT = """You are a narrative synthesizer for NVS Semantic Observatory (Gemmina Intelligence LLC).

Given the source article below, write a concise analytical narrative (150-300 words).
Focus on factual structure, epistemic confidence, and strategic domains.
Do not include markdown headers or bullet lists.

--- ARTICLE ---
{article}
--- END ---
"""


class NarrativePipeline:
    def __init__(self, annotator_client: SemanticAnnotatorClient | None = None, state_service: StateService | None = None):
        self.annotator_client = annotator_client or SemanticAnnotatorClient()
        self.state_service = state_service or StateService()

    def build_prompt(self, article: str) -> str:
        return NARRATIVE_PROMPT.format(article=article.strip())

    async def run(self, db: Session, article: str, origin: str = "us") -> dict[str, Any]:
        prompt = self.build_prompt(article)
        narrative, provider_used = await generate_narrative(prompt, origin)

        # Which backend Semantic Annotator uses internally is not passed
        # here and is not this pipeline's concern - see
        # runtime/services/semantic_annotator_client.py's module docstring.
        result = await self.annotator_client.annotate(narrative)
        tags = result.tags.to_legacy_dict()
        state_hash = crystallize_state_hash(narrative, tags, origin)
        epistemic = compute_epistemic_diffusion_state(tags)

        record = self.state_service.create(
            db,
            state_hash=state_hash,
            event_id=derive_event_id(article),
            narrative=narrative,
            tags=tags,
            subject_origin=origin,
            schema_version=SCHEMA_VERSION,
            epistemic_diffusion_state=epistemic,
            article=article,
            provider=provider_used,
        )
        return record.to_dict()
