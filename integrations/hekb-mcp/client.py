"""HTTP client for the hekb-runtime REST API (EXP-7100, C++ engine).

Endpoint shapes verified against ``hekb-runtime/src/api/rest_server.cpp``
(RestServer::registerRoutes). This client only wraps routes that actually
exist server-side — see hekb_mcp/docs/EXPERIMENT_REPORT.md for the full
existence audit. It does not retry, cache, or paginate; a single hekb-runtime
process is assumed reachable at ``base_url``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8080"


class HekbRuntimeError(RuntimeError):
    """Raised for any non-2xx response from hekb-runtime, or a transport failure."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class HekbObject:
    id: int
    type: str
    version: int
    created_ns: int
    updated_ns: int
    potential: float
    energy: float
    curvature: float
    flux_magnitude: float
    label: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "HekbObject":
        return cls(
            id=data["id"],
            type=data["type"],
            version=data["version"],
            created_ns=data["created_ns"],
            updated_ns=data["updated_ns"],
            potential=data["potential"],
            energy=data["energy"],
            curvature=data["curvature"],
            flux_magnitude=data["flux_magnitude"],
            label=data["label"],
        )


@dataclass
class HekbMorphism:
    id: int
    source: int
    target: int
    relation: str
    confidence: float
    energy: float
    curvature: float
    entropy: float
    distance: float
    causality: float
    time: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "HekbMorphism":
        return cls(
            id=data["id"],
            source=data["source"],
            target=data["target"],
            relation=data["relation"],
            confidence=data["confidence"],
            energy=data["energy"],
            curvature=data["curvature"],
            entropy=data["entropy"],
            distance=data["distance"],
            causality=data["causality"],
            time=data["time"],
        )


@dataclass
class GeodesicResult:
    found: bool
    total_cost: float
    path: list[int]


class HekbRuntimeClient:
    """Thin synchronous wrapper over hekb-runtime's REST API."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(base_url=base_url, transport=transport, timeout=5.0)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HekbRuntimeClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
        except httpx.TransportError as exc:
            raise HekbRuntimeError(f"transport error calling {path}: {exc}") from exc
        if response.status_code == 404:
            raise HekbRuntimeError(f"not_found: {path}", status_code=404)
        if response.status_code >= 400:
            raise HekbRuntimeError(f"hekb-runtime error {response.status_code} on {path}", status_code=response.status_code)
        return response.json()

    def get_object(self, object_id: int) -> HekbObject:
        return HekbObject.from_json(self._get(f"/objects/{object_id}"))

    def create_object(
        self,
        type: str = "observation",
        label: str = "",
        potential: float = 0.0,
        energy: float = 0.0,
        curvature: float = 0.0,
        flux_magnitude: float = 0.0,
    ) -> int:
        body = {
            "type": type,
            "label": label,
            "potential": potential,
            "energy": energy,
            "curvature": curvature,
            "flux_magnitude": flux_magnitude,
        }
        try:
            response = self._client.post("/objects", json=body)
        except httpx.TransportError as exc:
            raise HekbRuntimeError(f"transport error calling POST /objects: {exc}") from exc
        if response.status_code >= 400:
            raise HekbRuntimeError(f"hekb-runtime error {response.status_code} on POST /objects", status_code=response.status_code)
        return int(response.json()["id"])

    def get_morphism(self, morphism_id: int) -> HekbMorphism:
        return HekbMorphism.from_json(self._get(f"/morphisms/{morphism_id}"))

    def query_morphisms(
        self,
        source: int | None = None,
        target: int | None = None,
        relation: str | None = None,
        min_confidence: float | None = None,
        min_energy: float | None = None,
    ) -> list[HekbMorphism]:
        params = {
            k: v
            for k, v in {
                "source": source,
                "target": target,
                "relation": relation,
                "min_confidence": min_confidence,
                "min_energy": min_energy,
            }.items()
            if v is not None
        }
        data = self._get("/query/morphisms", params=params)
        return [HekbMorphism.from_json(m) for m in data.get("morphisms", [])]

    def query_neighborhood(self, seed: int, max_hops: int = 1) -> list[dict[str, Any]]:
        data = self._get("/query/neighborhood", params={"seed": seed, "max_hops": max_hops})
        return data.get("neighbors", [])

    def query_geodesic(self, source: int, target: int) -> GeodesicResult:
        data = self._get("/query/geodesic", params={"source": source, "target": target})
        return GeodesicResult(found=data["found"], total_cost=data.get("total_cost", 0.0), path=data.get("path", []))

    def query_topology(self) -> list[list[int]]:
        data = self._get("/query/topology")
        return data.get("components", [])

    def health(self) -> dict[str, Any]:
        return self._get("/health")
