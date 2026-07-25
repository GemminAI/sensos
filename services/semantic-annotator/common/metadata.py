"""Metadata generation - deterministic, no backend/LLM call, no fabricated
values. Shared under common/ (not app/) because the future CTG Engine
consumes this same shape for every Annotation it reads - see
app/schemas.py::MetadataBlock.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from common.version import ENGINE_VERSION


def build_metadata(*, text: str, provider: str, model: str) -> dict[str, object]:
    return {
        "annotation_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.0",
        "engine": "semantic-annotator",
        "engine_version": ENGINE_VERSION,
        "provider": provider,
        "model": model,
        "input_length": len(text),
    }
