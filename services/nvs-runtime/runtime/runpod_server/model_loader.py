"""Llama-3-8B-Instruct model and tokenizer loading with singleton caching."""

from __future__ import annotations

from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

_model: Any | None = None
_tokenizer: Any | None = None
_model_id: str | None = None


def load_model(model_id: str, device: str) -> tuple[Any, Any]:
    """Load model and tokenizer in BF16 with device_map=auto; cache at module level."""
    global _model, _tokenizer, _model_id

    if _model is not None and _tokenizer is not None and _model_id == model_id:
        return _model, _tokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    model.eval()

    _model = model
    _tokenizer = tokenizer
    _model_id = model_id
    return _model, _tokenizer


def get_model() -> Any:
    """Return cached model; raises if load_model has not been called."""
    if _model is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")
    return _model


def get_tokenizer() -> Any:
    """Return cached tokenizer; raises if load_model has not been called."""
    if _tokenizer is None:
        raise RuntimeError("Tokenizer not loaded. Call load_model() first.")
    return _tokenizer
