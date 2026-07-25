"""Sidecar store for semantic coordinate vectors (theta).

GAP-FILLING COMPONENT — documented in EXPERIMENT_REPORT.md, not a silent
workaround: hekb-runtime's HEXTObject schema has no vector/embedding field
(only scalar potential/energy/curvature/flux_magnitude — confirmed by
direct inspection of hekb-runtime/include/hekb/object.hpp and the REST
wire shapes in rest_server.cpp). RFC-NVS-0100 requires a real semantic
coordinate theta (384-dimensional here). Rather than lossily cramming a
384-dim vector into 4 scalar fields, or silently inventing a new
hekb-runtime schema field (out of scope — "do not redesign the
architecture"), this stores theta alongside the HEXTObject id in a plain
JSON sidecar file. A real Generation-3 implementation would need a
first-class vector field on HEXTObject (or an external vector store) —
this is exactly the kind of gap this experiment exists to surface.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

DEFAULT_STORE_PATH = Path(__file__).parent / "data" / "theta_store.json"


class ThetaStore:
    def __init__(self, path: str | Path = DEFAULT_STORE_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self._path.exists():
            self._path.write_text("{}")

    def _read_all(self) -> dict[str, Any]:
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def save(self, object_id: int, theta: list[float], metadata: dict[str, Any] | None = None) -> None:
        with self._lock:
            data = self._read_all()
            data[str(object_id)] = {"theta": theta, "metadata": metadata or {}}
            self._path.write_text(json.dumps(data))

    def load(self, object_id: int) -> dict[str, Any] | None:
        data = self._read_all()
        return data.get(str(object_id))

    def clear(self) -> None:
        with self._lock:
            self._path.write_text("{}")
