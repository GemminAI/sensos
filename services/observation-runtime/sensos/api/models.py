"""FastAPI request/response models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CycleRequest(BaseModel):
    prompt: str = Field(..., description="Initial reality stream input")
    max_iterations: int = Field(default=4, ge=1, le=32)
    runtime_backend: Optional[str] = Field(
        default=None,
        description="Runtime backend id (claude_cli, claude_api, gpt, gemini, local_llm, mock)",
    )
    verbose: bool = False


class CycleResponse(BaseModel):
    outcome: str
    steps_executed: int
    final_decision: Optional[str] = None
    final_risk: Optional[float] = None
    runtime_name: str


class HealthResponse(BaseModel):
    status: str
    version: str
    subsystems: Dict[str, str]


class RuntimePluginInfo(BaseModel):
    name: str
    backend: str
    available: bool
    capabilities: Dict[str, Any]


class RuntimeListResponse(BaseModel):
    plugins: List[RuntimePluginInfo]
