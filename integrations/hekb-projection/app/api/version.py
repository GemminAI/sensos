from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter()


class VersionResponse(BaseModel):
    name: str
    version: str


@router.get("/version")
def version() -> VersionResponse:
    return VersionResponse(name=settings.app_name, version=settings.version)
