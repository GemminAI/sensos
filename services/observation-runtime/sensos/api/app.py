"""
SensOS FastAPI Application Factory.

Provides HTTP endpoints for future API integration while preserving
the kernel-native scheduler pipeline.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException

from sensos import __version__
from sensos.api.models import (
    CycleRequest,
    CycleResponse,
    HealthResponse,
    RuntimeListResponse,
    RuntimePluginInfo,
)
from sensos.kernel.executive import KernelExecutive
from sensos.memory.crystallized import CrystallizedMemoryStorage
from sensos.runtime.plugin import RuntimeBackend
from sensos.runtime.registry import RuntimePluginRegistry


def _resolve_backend(backend: str | None) -> RuntimeBackend:
    if backend is None:
        return RuntimeBackend.CLAUDE_CLI
    try:
        return RuntimeBackend(backend)
    except ValueError as exc:
        valid = ", ".join(b.value for b in RuntimeBackend)
        raise HTTPException(status_code=400, detail=f"Unknown runtime backend '{backend}'. Valid: {valid}") from exc


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(
        title="SensOS Kernel API",
        description="Observation-Centered Reality OS v2.0 — Kernel HTTP Interface",
        version=__version__,
        lifespan=lifespan,
    )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            subsystems={
                "observation_engine": "ready",
                "dak": "ready",
                "runtime_plugins": "ready",
                "memory": "ready",
            },
        )

    @app.get("/version")
    async def version() -> dict:
        return {"name": "SensOS Kernel", "version": __version__}

    @app.get("/runtime/plugins", response_model=RuntimeListResponse)
    async def list_runtime_plugins() -> RuntimeListResponse:
        plugins = []
        for backend in RuntimePluginRegistry.list_backends():
            plugin = RuntimePluginRegistry.create(backend)
            caps = plugin.get_capabilities()
            plugins.append(
                RuntimePluginInfo(
                    name=plugin.get_name(),
                    backend=caps.backend.value,
                    available=plugin.is_available(),
                    capabilities={
                        "supports_streaming": caps.supports_streaming,
                        "supports_system_directive": caps.supports_system_directive,
                        "requires_api_key": caps.requires_api_key,
                        "cli_binary": caps.cli_binary,
                        "model_id": caps.model_id,
                        "extra": caps.extra,
                    },
                )
            )
        return RuntimeListResponse(plugins=plugins)

    @app.post("/kernel/cycle", response_model=CycleResponse)
    async def run_kernel_cycle(request: CycleRequest) -> CycleResponse:
        backend = _resolve_backend(request.runtime_backend)
        runtime = RuntimePluginRegistry.create(backend)
        executive = KernelExecutive(
            runtime=runtime,
            memory=CrystallizedMemoryStorage(),
            verbose=request.verbose,
        )
        result = executive.run_cycle_structured(
            request.prompt,
            max_iterations=request.max_iterations,
        )
        return CycleResponse(
            outcome=result.outcome,
            steps_executed=result.steps_executed,
            final_decision=result.final_decision.value if result.final_decision else None,
            final_risk=result.final_risk,
            runtime_name=runtime.get_name(),
        )

    return app
