"""Single source of truth for this service's own release version.

Distinct from app.schemas.ANNOTATION_SCHEMA_VERSION (the wire schema
version) - this is the semantic-annotator engine/build version. Shared
under common/ because the future CTG Engine also needs to know which
Semantic Annotator build produced a given Annotation (see metadata.py).
"""

from __future__ import annotations

ENGINE_VERSION = "1.0.0"
