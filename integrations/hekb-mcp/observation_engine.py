"""RFC-NVS-0100 Observation Engine: NVS.SysObserve implementation.

Projects natural-language text into a semantic coordinate theta (Hypothesis
0, Projection Existence), resolves the nearest Chart/Attractor (Hypothesis
3), supports round-trip rendering for residual measurement (Hypotheses 1
and 4), and creates a HEXT Observation Object in the real hekb-runtime
engine for each observation.

Encoder choice, stated plainly: no text-embedding component of any kind
existed anywhere in this repository before this experiment (verified by
exhaustive grep across the whole tree — 35TAG is a mostly hash-filled
identification vector, not a semantic embedding; DAK's hidden-state
recorder only consumes vectors that already exist). This module adds
`sentence-transformers` (paraphrase-multilingual-MiniLM-L12-v2, 384-dim,
chosen for real multilingual — including Japanese — semantic coverage) as
a new, narrowly-scoped dependency to make Projection Existence possible at
all. See EXPERIMENT_REPORT_RFC0100.md for the numbers this actually
produces against the RFC's stated MUST thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from hekb_mcp.client import HekbRuntimeClient
from hekb_mcp.reference_corpus import ATTRACTORS
from hekb_mcp.theta_store import ThetaStore

try:
    from hekb_mcp.tags import extract_tag_vector

    _TAG_EXTRACTOR_AVAILABLE = True
except Exception:  # pragma: no cover - defensive; see module docstring
    _TAG_EXTRACTOR_AVAILABLE = False


class SemanticEncoder(Protocol):
    dimension: int

    def encode(self, text: str) -> np.ndarray: ...


class SentenceTransformerEncoder:
    """Real encoder. Lazily loads the model on first use (avoids paying the
    ~85s download/load cost for code paths that never call it, e.g. imports
    in unrelated tests)."""

    MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
    dimension = 384

    def __init__(self) -> None:
        self._model = None

    def _ensure_loaded(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.MODEL_NAME)

    def encode(self, text: str) -> np.ndarray:
        self._ensure_loaded()
        vec = self._model.encode([text])[0]
        return np.asarray(vec, dtype=np.float64)

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        self._ensure_loaded()
        return np.asarray(self._model.encode(texts), dtype=np.float64)


def l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm < 1e-12:
        return vec
    return vec / norm


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def reality_distance(text_a: str, text_b: str, encoder: SemanticEncoder) -> float:
    """d_R(q, q_hat) — operationalized as 1 - cosine_similarity in the
    encoder's own embedding space. This is the standard proxy used
    whenever no independent "Reality space" metric exists (see
    EXPERIMENT_REPORT_RFC0100.md, Deviations, for why this is a real but
    stated simplification rather than an independently-grounded distance)."""
    ea = encoder.encode(text_a)
    eb = encoder.encode(text_b)
    return 1.0 - cosine_similarity(ea, eb)


@dataclass
class Projection:
    theta: np.ndarray  # unit-normalized, dimension == encoder.dimension
    raw_norm: float  # ||encoder.encode(text)|| before normalization


class Projector:
    """Pi: Reality -> M (Hypothesis 0). Total function over any string
    input by construction (encode() + normalize() are both total), so
    Projection Existence holds trivially for this implementation — the
    real empirical question (tested separately) is whether the resulting
    theta is USEFUL (Hypotheses 1-4), not whether it exists."""

    def __init__(self, encoder: SemanticEncoder) -> None:
        self.encoder = encoder

    def project(self, text: str) -> Projection:
        raw = self.encoder.encode(text)
        theta = l2_normalize(raw)
        return Projection(theta=theta, raw_norm=float(np.linalg.norm(raw)))


@dataclass
class ResolutionResult:
    chart_id: str
    attractor_id: str
    similarity: float
    runner_up_attractor_id: str
    runner_up_similarity: float

    @property
    def margin(self) -> float:
        return self.similarity - self.runner_up_similarity


class AttractorResolver:
    """Nearest-centroid classifier over ATTRACTORS' canonical descriptions.

    This operationalizes RFC-NVS-0100 Hypothesis 3's P(Chart, Attractor |
    q, C): the context C in the RFC's test scenarios (5.1) is baked into
    each query's own wording (every example query is already
    self-disambiguating), so no separate context input is modeled here —
    documented as a stated simplification, not a silent one.
    """

    def __init__(self, encoder: SemanticEncoder) -> None:
        self.encoder = encoder
        self._reference_theta: dict[str, np.ndarray] = {}
        projector = Projector(encoder)
        for attractor_id, definition in ATTRACTORS.items():
            self._reference_theta[attractor_id] = projector.project(definition.canonical_description).theta

    def resolve(self, theta: np.ndarray) -> ResolutionResult:
        scored = sorted(
            ((aid, cosine_similarity(theta, ref)) for aid, ref in self._reference_theta.items()),
            key=lambda pair: pair[1],
            reverse=True,
        )
        top_id, top_sim = scored[0]
        runner_id, runner_sim = scored[1]
        return ResolutionResult(
            chart_id=ATTRACTORS[top_id].chart_id,
            attractor_id=top_id,
            similarity=top_sim,
            runner_up_attractor_id=runner_id,
            runner_up_similarity=runner_sim,
        )


class RetrievalRenderer:
    """Render(theta) -> text, operationalized as nearest-neighbor retrieval
    over the same canonical-description pool the resolver uses.

    Stated deviation: RFC-NVS-0100 (and the broader HEKB-MCP design it
    builds on) envisions Render() as an LLM paraphrasing geometric metadata
    into natural language. No generative LLM Renderer is wired into this
    experiment (no LLM API credentials assumed available; building one is
    a separate, larger concern — the "LLM Renderer" component of the
    wider TAG/GAG architecture, not the Observation Engine this RFC scopes
    to). Nearest-neighbor retrieval is a standard, well-defined substitute
    that keeps the whole pipeline self-contained and reproducible; see
    EXPERIMENT_REPORT_RFC0100.md for what this choice does and doesn't
    prove about round-trip residual.
    """

    def __init__(self, encoder: SemanticEncoder) -> None:
        self.encoder = encoder
        self.resolver = AttractorResolver(encoder)

    def render(self, theta: np.ndarray) -> str:
        result = self.resolver.resolve(theta)
        return ATTRACTORS[result.attractor_id].canonical_description


@dataclass
class ObservationResult:
    object_id: int
    text: str
    theta: list[float]
    raw_norm: float
    resolution: ResolutionResult
    tag_vector_available: bool
    tag_vector: list[float] | None


class ObservationEngine:
    """Ties Projector + AttractorResolver + hekb-runtime object creation +
    theta_store together into NVS.SysObserve(text)."""

    def __init__(
        self,
        client: HekbRuntimeClient,
        encoder: SemanticEncoder | None = None,
        theta_store: ThetaStore | None = None,
    ) -> None:
        self.encoder = encoder or SentenceTransformerEncoder()
        self.projector = Projector(self.encoder)
        self.resolver = AttractorResolver(self.encoder)
        self.client = client
        self.theta_store = theta_store or ThetaStore()

    def observe(self, text: str) -> ObservationResult:
        projection = self.projector.project(text)
        resolution = self.resolver.resolve(projection.theta)

        tag_vector: list[float] | None = None
        if _TAG_EXTRACTOR_AVAILABLE:
            try:
                tag_vector = extract_tag_vector(text).tolist()
            except Exception:
                tag_vector = None

        # Scalars stored on the real HEXTObject are DERIVED signals, not
        # theta itself (hekb-runtime has no vector field — see
        # theta_store.py docstring): potential/energy encode resolution
        # confidence, curvature encodes novelty (dissimilarity to the
        # nearest known attractor), flux_magnitude is the pre-normalization
        # embedding norm.
        object_id = self.client.create_object(
            type="observation",
            label=text[:80],
            potential=resolution.similarity,
            energy=resolution.margin,
            curvature=1.0 - resolution.similarity,
            flux_magnitude=projection.raw_norm,
        )

        self.theta_store.save(
            object_id,
            theta=projection.theta.tolist(),
            metadata={
                "text": text,
                "chart_id": resolution.chart_id,
                "attractor_id": resolution.attractor_id,
                "similarity": resolution.similarity,
                "tag_vector_available": tag_vector is not None,
            },
        )

        return ObservationResult(
            object_id=object_id,
            text=text,
            theta=projection.theta.tolist(),
            raw_norm=projection.raw_norm,
            resolution=resolution,
            tag_vector_available=tag_vector is not None,
            tag_vector=tag_vector,
        )
