from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_storage_backend
from app.models.storage_profile import StorageProfile
from app.storage.protocol import StorageBackend

router = APIRouter()


@router.get("/storage/profile")
def storage_profile(
    backend: Annotated[StorageBackend, Depends(get_storage_backend)],
) -> StorageProfile:
    return backend.profile()
