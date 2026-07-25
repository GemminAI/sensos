"""FastAPI routes for HEXT STREAM Runtime v1.0."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from hext_stream.observation.driver import ObservationDriver
from hext_stream.observation.errors import ObservationRuntimeError
from hext_stream.runtime.stream_runtime import HEXTStream
from hext_stream.schema.base import HextObject
from hext_stream.schema.replay import ReplayMode, ReplayRequest

router = APIRouter()


class PublishBody(BaseModel):
    source: str
    type: str
    version: str = "1.0.0"
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None
    timestamp: datetime | None = None


def _runtime(request: Request):
    return request.app.state.runtime


def _observation_driver(request: Request) -> ObservationDriver:
    return request.app.state.observation_driver


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    return _runtime(request).health()


@router.get("/metrics")
def metrics(request: Request) -> dict[str, Any]:
    return _runtime(request).metrics_dict()


@router.get("/topics")
def topics(request: Request) -> dict[str, list[str]]:
    rt = _runtime(request)
    return {"topics": rt.router.topics}


@router.post("/publish/{topic}")
def publish(topic: str, body: PublishBody, request: Request) -> dict[str, Any]:
    rt = _runtime(request)
    driver = _observation_driver(request)
    try:
        # RFC-HEXT013 §2 Rule 1: /publish is a raw-input ingestion path, so
        # it is routed through the Observation Driver rather than
        # constructing HextObject inline.
        obj = driver.ingest(
            stream=topic,
            source=body.source,
            type=body.type,
            version=body.version,
            payload=body.payload,
            metadata=body.metadata,
            id=body.id,
            timestamp=body.timestamp,
        )
        event_id = rt.publish(topic, obj)
        return {"status": "published", "topic": topic, "event_id": event_id, "object_id": obj.id}
    except ObservationRuntimeError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/history/{topic}")
def history(
    topic: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=10_000),
) -> dict[str, Any]:
    rt = _runtime(request)
    try:
        events = rt.history(topic, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "topic": topic,
        "count": len(events),
        "events": [e.to_envelope() for e in events],
    }


@router.get("/replay/{topic}")
def replay(
    topic: str,
    request: Request,
    mode: ReplayMode = Query(default=ReplayMode.LAST_N),
    from_id: str | None = None,
    from_timestamp: datetime | None = None,
    last_n: int = Query(default=100, ge=1, le=10_000),
) -> dict[str, Any]:
    rt = _runtime(request)
    req = ReplayRequest(
        topic=topic,
        mode=mode,
        from_id=from_id,
        from_timestamp=from_timestamp,
        last_n=last_n,
    )
    try:
        events = rt.replay(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "topic": topic,
        "mode": mode.value,
        "count": len(events),
        "events": [e.to_envelope() for e in events],
    }


@router.get("/subscribe/{topic}")
async def subscribe_sse(topic: str, request: Request) -> StreamingResponse:
    """Server-Sent Events subscription for a topic."""
    rt = _runtime(request)
    try:
        rt.router.validate(topic)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    queue: asyncio.Queue[str] = asyncio.Queue()

    def _callback(obj: HextObject) -> None:
        queue.put_nowait(json.dumps(obj.to_envelope()))

    handle = rt.subscribe(topic, _callback)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            rt.unsubscribe(handle)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
