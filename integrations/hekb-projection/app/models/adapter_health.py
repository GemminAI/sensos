from enum import StrEnum

from pydantic import BaseModel


class AdapterHealthStatus(StrEnum):
    HEALTHY = "healthy"
    NOT_IMPLEMENTED = "not_implemented"
    UNHEALTHY = "unhealthy"


class AdapterHealth(BaseModel):
    name: str
    status: AdapterHealthStatus
    detail: str | None = None
