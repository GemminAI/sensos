"""Semantic Annotator FastAPI application.

Semantic Annotator is NOT a reasoning engine. It does not think, infer,
measure, or compute geometry - it describes what is present in a text and
nothing more. See README.md for the full scope statement and the cascade
this service sits in: Natural Language -> Semantic Annotator -> CTG Engine
-> Semantic Measurement Framework -> Generation.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.annotator import annotate_text
from app.schemas import AnnotateRequest, Annotation, HealthResponse, VersionResponse
from common.version import ENGINE_VERSION

app = FastAPI(
    title="Semantic Annotator",
    description=(
        "Annotation stage of the CTG cascade (Natural Language -> Semantic "
        "Annotator -> CTG Engine -> Semantic Measurement Framework -> "
        "Generation). Describes meaning - 35TAG generation, Subject/Entity/"
        "Event/Time/Location extraction, metadata, confidence. Never "
        "measures it: no Geometry, Curvature, TD, TH, Trajectory, "
        "Holonomy, Geodesic, Physics, Fiber Bundle, Category Theory, or "
        "Semantic Dynamics live here - that is the CTG Engine's exclusive "
        "responsibility."
    ),
    version=ENGINE_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    return VersionResponse(engine_version=ENGINE_VERSION)


def _annotate(request: AnnotateRequest) -> Annotation:
    """Shared handler body - kept separate from the route decorator so a
    future POST /annotate/text can alias directly to it, and sibling
    POST /annotate/document / POST /annotate/batch routes can reuse it
    without restructuring this function, per the input-shape extension
    planned for a later release (see README.md Future Expansion)."""
    try:
        result = annotate_text(request.text, request.provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        message = str(exc)
        if "is not set" in message:
            raise HTTPException(status_code=503, detail=message) from exc
        raise HTTPException(status_code=502, detail=message) from exc
    return Annotation.model_validate(result)


@app.post("/annotate", response_model=Annotation)
def annotate(request: AnnotateRequest) -> Annotation:
    return _annotate(request)
