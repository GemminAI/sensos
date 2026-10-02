"""sensos smoke: minimal, real Runtime connectivity test.

Confirms the chain Installer -> SensOS Runtime -> Semantic Annotator ->
RuntimeBridge -> Linux backend is actually wired together, reusing the
existing `VLLMRuntimeBridge`/`LLMAnnotator` unchanged -- this module
adds no new inference or parsing logic of its own. No fake PASS: if the
backend URL/model are unset, or the connection or response fails, this
reports which layer failed and why, never a fabricated success.

Configuration follows the exact convention already established by
`semantic_annotator/scripts/sa001_eval.py`: `RUNTIME_BRIDGE_URL` (the
vLLM server's OpenAI-compatible base URL). The model id is read from
`SENSOS_MODEL_ID` (`sa001_eval.py`'s `GEMMA_MODEL_ID` name was
Gemma-specific; this is not). Per explicit design decision, no default
model is assumed -- an unset model id is a FAIL, not a guess.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime

from semantic_annotator.llm_annotator import LLMAnnotationError, LLMAnnotator
from semantic_annotator.models import Observation
from semantic_annotator.runtime_bridge import RuntimeBridgeError, VLLMRuntimeBridge

_SAMPLE_TEXT = "A red car is parked outside the main entrance."


@dataclass(frozen=True, slots=True)
class SmokeResult:
    passed: bool
    stage: str
    detail: str


def run_smoke(*, base_url: str | None = None, model: str | None = None) -> SmokeResult:
    if base_url is None:
        base_url = os.environ.get("RUNTIME_BRIDGE_URL")
    if model is None:
        model = os.environ.get("SENSOS_MODEL_ID")

    if not base_url:
        return SmokeResult(
            False,
            "configuration",
            "RUNTIME_BRIDGE_URL is not set; point it at a running vLLM server "
            "(e.g. http://localhost:8000)",
        )
    if not model:
        return SmokeResult(
            False,
            "configuration",
            "SENSOS_MODEL_ID is not set; specify the model vLLM is serving "
            "(no default model is assumed)",
        )

    bridge = VLLMRuntimeBridge(base_url=base_url, model=model)
    annotator = LLMAnnotator(bridge)
    observation = Observation(
        id="smoke-1",
        source="sensos-smoke",
        timestamp=datetime.now(UTC),
        payload={"text": _SAMPLE_TEXT},
    )

    try:
        annotated = annotator.annotate(observation)
    except RuntimeBridgeError as exc:
        return SmokeResult(False, "RuntimeBridge (vLLM connection)", str(exc))
    except LLMAnnotationError as exc:
        return SmokeResult(False, "LLMAnnotator (response parsing)", str(exc))

    return SmokeResult(
        True,
        "AnnotatedObservation",
        f"{len(annotated.annotations)} annotation(s) produced",
    )
