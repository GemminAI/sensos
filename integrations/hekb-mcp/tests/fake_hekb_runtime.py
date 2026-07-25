"""In-process fake of hekb-runtime's REST API, via httpx.MockTransport.

This does NOT reimplement or re-verify hekb-runtime's own Dijkstra/BFS
logic (that is EXP-7100's own C++ test suite's job — out of scope here).
It only fakes the wire responses so hekb_mcp's client/tool/security code
can be tested deterministically without building the C++ binary. See
task #7 / EXPERIMENT_REPORT.md for the separate live-binary smoke test.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class FakeHekbRuntime:
    def __init__(self) -> None:
        self.objects: dict[int, dict[str, Any]] = {}
        self.morphisms: dict[int, dict[str, Any]] = {}
        self.geodesic_responses: dict[tuple[int, int], dict[str, Any]] = {}
        self._next_object_id = 1

    def seed_object(self, object_id: int, **fields: Any) -> None:
        base = {
            "id": object_id,
            "type": "observation",
            "version": 1,
            "created_ns": 0,
            "updated_ns": 0,
            "potential": 0.0,
            "energy": 0.0,
            "curvature": 0.0,
            "flux_magnitude": 0.0,
            "label": "",
        }
        base.update(fields)
        self.objects[object_id] = base

    def seed_geodesic(self, source: int, target: int, found: bool, total_cost: float, path: list[int]) -> None:
        self.geodesic_responses[(source, target)] = {"found": found, "total_cost": total_cost, "path": path}

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            params = dict(request.url.params)

            if path == "/health":
                return httpx.Response(200, json={"status": "ok"})

            if path == "/objects" and request.method == "POST":
                body = json.loads(request.content)
                object_id = self._next_object_id
                self._next_object_id += 1
                self.seed_object(object_id, **body)
                return httpx.Response(200, json={"id": object_id})

            if path.startswith("/objects/"):
                object_id = int(path.rsplit("/", 1)[-1])
                obj = self.objects.get(object_id)
                if obj is None:
                    return httpx.Response(404, json={"error": "not_found"})
                return httpx.Response(200, json=obj)

            if path.startswith("/morphisms/"):
                morphism_id = int(path.rsplit("/", 1)[-1])
                m = self.morphisms.get(morphism_id)
                if m is None:
                    return httpx.Response(404, json={"error": "not_found"})
                return httpx.Response(200, json=m)

            if path == "/query/geodesic":
                source = int(params["source"])
                target = int(params["target"])
                result = self.geodesic_responses.get((source, target), {"found": False, "total_cost": 0.0, "path": []})
                return httpx.Response(200, json=result)

            if path == "/query/morphisms":
                matches = list(self.morphisms.values())
                return httpx.Response(200, json={"morphisms": matches})

            if path == "/query/neighborhood":
                return httpx.Response(200, json={"neighbors": []})

            if path == "/query/topology":
                return httpx.Response(200, json={"components": [list(self.objects.keys())]})

            return httpx.Response(404, json={"error": "no_such_route"})

        return httpx.MockTransport(handler)
