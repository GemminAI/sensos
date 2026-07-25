from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StorageCapabilities(BaseModel):
    """Capability flags a StorageBackend declares about itself.

    Field set mirrors the RFC-HEKB08 draft's per-storage-class capability
    maps (append_only / relational / blob); extra keys are allowed so a
    future backend can declare capabilities not yet enumerated here.
    """

    model_config = ConfigDict(extra="allow")

    transactions: bool = False
    ordered_write: bool = False
    sequential_scan: bool = False
    random_update: bool = False
    referential_integrity: bool = False
    time_to_live: bool = False
    dense_array_optimized: bool = False
    vector_search_index: bool = False


class StorageProfile(BaseModel):
    """Declarative description of a StorageBackend's persistence properties."""

    storage_class: str
    retention: str | None = None
    capabilities: StorageCapabilities
    metadata: dict[str, Any] = Field(default_factory=dict)
