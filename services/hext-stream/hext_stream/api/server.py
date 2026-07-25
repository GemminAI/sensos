"""HEXT STREAM FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from hext_stream.api.routes import router
from hext_stream.observation.driver import ObservationDriver
from hext_stream.runtime.stream_runtime import HEXTStream, StreamRuntime, load_config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime: StreamRuntime = app.state.runtime
    yield
    runtime.close()


def create_app(*, runtime: StreamRuntime | None = None) -> FastAPI:
    rt = runtime or HEXTStream.configure(config=load_config())
    app = FastAPI(
        title="HEXT STREAM Runtime",
        version="1.0.0",
        description="Canonical semantic flow runtime for SensOS, TrajectoryDB, DAK, and STLE.",
        lifespan=lifespan,
    )
    app.state.runtime = rt
    # RFC-HEXT013 §2: the Observation Driver is the sole permitted entry
    # point for raw external input; /publish is that boundary.
    app.state.observation_driver = ObservationDriver()
    app.include_router(router)
    return app


app = create_app()
