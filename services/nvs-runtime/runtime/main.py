import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from runtime.api import api_router
from runtime.auth import AuthConfig, validate_startup_credentials
from runtime.core.config import get_settings
from runtime.core.exceptions import RuntimeErrorBase
from runtime.db.session import init_db
from runtime.gateway.http_pool import close_all_pooled_clients
from runtime.gateway.kernel_gateway import KernelGateway
from runtime.services.forward_worker import ForwardWorker
from runtime.services.redis_service import RedisService
from runtime.services.semantic_annotator_client import SemanticAnnotatorClient

settings = get_settings()
_forward_worker: ForwardWorker | None = None


def _auth_config_path() -> Path:
    candidates = [
        os.getenv("NVS_AUTH_CONFIG", ""),
        "/app/config/auth.yaml",
        "configs/auth.yaml",
        "config/auth.yaml",
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw)
        if path.is_file():
            return path
    return Path("configs/auth.yaml")

app = FastAPI(
    title="NVS MCP Runtime Server",
    version="0.1.0-p1",
    description="RFC-NVS42 v0.3 — Agent Registry, Session Management, SEP Event Transport",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:4174",
        "http://nvs-browser-console:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:4175",
        "http://nvs-browser-rc1:5175",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://nvs-browser-next:3000",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)

from runtime.api.routes_browser import generate_router, states_router
from runtime.api.routes_events import router as events_router

app.include_router(generate_router, prefix="/runtime", tags=["browser-rc1"])
app.include_router(states_router, tags=["browser-rc1"])
app.include_router(events_router, tags=["browser-rc2c"])


@app.exception_handler(RuntimeErrorBase)
async def runtime_error_handler(_request, exc: RuntimeErrorBase):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


@app.on_event("startup")
async def on_startup():
    global _forward_worker
    if os.getenv("TESTING"):
        return
    # Refuse template JWT secrets (e.g. CHANGE_ME) before serving traffic.
    validate_startup_credentials(AuthConfig.from_yaml(_auth_config_path()))
    init_db()
    # Version Negotiation: refuse to finish starting up against a Semantic
    # Annotator whose schema_version this Runtime build doesn't know how
    # to parse - see semantic_annotator_client.py::check_version_compatibility.
    await SemanticAnnotatorClient().check_version_compatibility()
    # EXP-Ubuntu011: Observation -> Queue -> Worker -> NVS. Ingest no longer
    # calls the kernel inline; this background task is what actually
    # delivers queued events.
    _forward_worker = ForwardWorker()
    await _forward_worker.start()


@app.on_event("shutdown")
async def on_shutdown():
    global _forward_worker
    if _forward_worker is not None:
        await _forward_worker.stop()
        _forward_worker = None
    await close_all_pooled_clients()


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready")
async def ready():
    redis_ok = RedisService().ping()
    kernel_ok = await KernelGateway().health_check()
    status = "ready" if redis_ok else "degraded"
    return {
        "status": status,
        "checks": {
            "redis": redis_ok,
            "kernel": kernel_ok,
            "postgres": True,
        },
    }
