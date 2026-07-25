from fastapi import FastAPI

from app.api.adapters import router as adapters_router
from app.api.health import router as health_router
from app.api.storage import router as storage_router
from app.api.version import router as version_router
from app.config import settings

app = FastAPI(title=settings.app_name, version=settings.version)

app.include_router(health_router)
app.include_router(version_router)
app.include_router(storage_router)
app.include_router(adapters_router)
