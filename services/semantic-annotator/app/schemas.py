"""Wire schema for the Semantic Annotator.

Semantic Annotator describes meaning; it does not measure it. Nothing in
this module may carry a geometric, coordinate, curvature, trilateration,
holonomy, geodesic, fiber-bundle, category-theoretic, or physics-flavored
quantity under any field name - that is the future CTG Engine's exclusive
responsibility (see README.md).

`reference` and `interpreter` are typed as concrete-model-or-None (not bare
None) so a future release can populate them with real data without a
breaking schema change - no extraction logic lives here for either today.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ProviderName = Literal["anthropic", "openai", "gemini"]

ANNOTATION_SCHEMA_VERSION = "1.0"


# ── tags ─────────────────────────────────────────────────────────────────

class T09Vector(BaseModel):
    security: float = 0.0
    economy: float = 0.0
    technology: float = 0.0
    resources: float = 0.0
    ideology: float = 0.0
    environment: float = 0.0


class ActorRole(BaseModel):
    actor_type: str
    actor_scale: str
    actor_perspective: str


class BiasComponent(BaseModel):
    emotional_load: float
    sentiment_gravity: list[float] = Field(..., min_length=2, max_length=2)


class TagsBlock(BaseModel):
    T09_strategic_interest_vector: T09Vector = Field(default_factory=T09Vector)
    T10_epistemic_confidence: float = Field(0.5, ge=0.0, le=1.0)
    T19_conflict_factuality_index: float = Field(0.0, ge=0.0, le=1.0)
    # Extension tags - None unless the annotation backend genuinely
    # returned a well-formed value; never guessed or defaulted.
    T03_predicate_type: str | None = None
    T07_actor_role: ActorRole | None = None
    T08_causality_direction: str | None = None
    T11_bias_component: BiasComponent | None = None
    T16_economic_transmission_path: list[str] | None = None


# ── subject ──────────────────────────────────────────────────────────────

class SubjectBlock(BaseModel):
    primary: str | None = None
    type: str | None = None
    description: str | None = None


# ── entities / events ────────────────────────────────────────────────────

class EntityItem(BaseModel):
    text: str
    type: str
    normalized: str | None = None
    salience: float | None = None


class EventItem(BaseModel):
    predicate: str
    participants: list[str] = Field(default_factory=list)
    predicate_type: str | None = None


# ── time / location ──────────────────────────────────────────────────────

class TimeBlock(BaseModel):
    absolute: str | None = None
    relative: str | None = None
    tense: str | None = None


class LocationBlock(BaseModel):
    primary: str | None = None
    type: str | None = None
    normalized: str | None = None


# ── future hooks (empty by design) ──────────────────────────────────────

class ReferenceAnnotation(BaseModel):
    """Empty placeholder. No extraction logic exists yet - see README.md
    Future Expansion. Kept as a typed model (not bare None) so a future
    release can populate it without a breaking schema change."""

    model_config = ConfigDict(extra="forbid")


class InterpreterAnnotation(BaseModel):
    """Empty placeholder. No extraction logic exists yet - see README.md
    Future Expansion. Kept as a typed model (not bare None) so a future
    release can populate it without a breaking schema change."""

    model_config = ConfigDict(extra="forbid")


# ── metadata / confidence (built in common/, modeled here) ─────────────

class MetadataBlock(BaseModel):
    annotation_id: str
    created_at: str
    schema_version: str = ANNOTATION_SCHEMA_VERSION
    engine: str = "semantic-annotator"
    engine_version: str
    provider: str
    model: str
    input_length: int


ConfidenceQuality = Literal["REAL", "DERIVED", "METADATA", "PLACEHOLDER", "UNAVAILABLE"]


class ConfidenceEntry(BaseModel):
    # Any, not float: a tag's echoed value can be a scalar (T10/T19), a
    # 6-axis vector (T09), an object (T07/T11), or a list (T16).
    value: Any | None = None
    quality: ConfidenceQuality
    reason: str | None = None


class ConfidenceBlock(BaseModel):
    overall: ConfidenceEntry
    tags: dict[str, ConfidenceEntry] = Field(default_factory=dict)
    subject: ConfidenceEntry
    entities: ConfidenceEntry
    events: ConfidenceEntry
    time: ConfidenceEntry
    location: ConfidenceEntry


# ── top-level envelope ───────────────────────────────────────────────────

class Annotation(BaseModel):
    version: str = ANNOTATION_SCHEMA_VERSION
    tags: TagsBlock
    subject: SubjectBlock
    entities: list[EntityItem] = Field(default_factory=list)
    events: list[EventItem] = Field(default_factory=list)
    time: TimeBlock
    location: LocationBlock
    reference: ReferenceAnnotation | None = None
    interpreter: InterpreterAnnotation | None = None
    metadata: MetadataBlock
    confidence: ConfidenceBlock


# ── request / misc response models ──────────────────────────────────────

class AnnotateRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Natural language text to annotate")
    provider: ProviderName = Field(default="anthropic", description="Annotation backend to use")


class HealthResponse(BaseModel):
    status: str = "ok"


class VersionResponse(BaseModel):
    engine: str = "semantic-annotator"
    engine_version: str
    schema_version: str = ANNOTATION_SCHEMA_VERSION
