"""sensos: installable entry point wiring Semantic Annotator's
RuntimeBridge onto a Linux inference backend (vLLM/CUDA).

Does not implement annotation, transport, or inference itself --
those responsibilities stay in `semantic_annotator` (RuntimeBridge,
VLLMRuntimeBridge, LLMAnnotator) unchanged. This package only adds an
installable `sensos` CLI (`doctor`, `smoke`) around it.
"""

from __future__ import annotations

__version__ = "0.1.0"
