from typing import Annotated

from fastapi import APIRouter, Depends

from app.models.adapter_health import AdapterHealth
from app.storage.adapters.registry import AdapterRegistry, get_adapter_registry

router = APIRouter()


@router.get("/adapters")
def list_adapters(
    registry: Annotated[AdapterRegistry, Depends(get_adapter_registry)],
) -> dict[str, str]:
    return {
        storage_class: type(adapter).__name__ for storage_class, adapter in registry.all().items()
    }


@router.get("/adapters/health")
def adapters_health(
    registry: Annotated[AdapterRegistry, Depends(get_adapter_registry)],
) -> list[AdapterHealth]:
    return [adapter.health() for adapter in registry.all().values()]
