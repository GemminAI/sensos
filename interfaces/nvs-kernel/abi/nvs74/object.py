"""RFC-NVS74 Observation Object implementation."""

from __future__ import annotations

import json
from typing import Any, Dict

from pydantic import BaseModel, Field


class ObservationObject(BaseModel):
    """
    RFC-NVS74 (Object ABI) Specification.

    Represents a single static semantic state O(t) compiled from reality observation.
    """

    step: int
    text: str
    metrics: Dict[str, float]
    state_hash: str = ""

    model_config = {"arbitrary_types_allowed": True}

    def model_post_init(self, __context: Any) -> None:
        if not self.state_hash:
            object.__setattr__(self, "state_hash", self.generate_state_hash())

    def generate_state_hash(self) -> str:
        """
        RFC-NVS78 Cryptographic Verification Protocol.
        Generates deterministic cognitive seal using normalized JSON structure.
        """
        payload = {
            "step": self.step,
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
        }
        serialized = json.dumps(payload, sort_keys=True)
        h = 5381
        for char in serialized:
            h = ((h << 5) + h) + ord(char)
        return f"SENSOS_HASH_{abs(h & 0xFFFFFFFF):08x}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "state_hash": self.state_hash,
            "metrics": self.metrics,
            "payload_preview": self.text[:70].replace("\n", " ") + "...",
        }

    @classmethod
    def from_legacy(cls, step: int, text: str, metrics: Dict[str, float], state_hash: str = "") -> "ObservationObject":
        """Construct from legacy constructor signature (backward compatibility)."""
        return cls(step=step, text=text, metrics=metrics, state_hash=state_hash or "")
