"""Autoregressive generation loop with CEWS (HiddenStateObserver) integration."""

from __future__ import annotations

from typing import Any

import torch

from observer_adapter import ObserverAdapter


def _resolve_device(model: Any) -> torch.device:
    if hasattr(model, "device"):
        return model.device
    return next(model.parameters()).device


def _sample_next_token(logits: torch.Tensor, temperature: float) -> torch.Tensor:
    if temperature <= 0.0:
        return logits.argmax(dim=-1)
    scaled = logits / temperature
    probs = torch.softmax(scaled, dim=-1)
    return torch.multinomial(probs, num_samples=1).squeeze(-1)


def generate_with_observer(
    prompt: str,
    model: Any,
    tokenizer: Any,
    adapter: ObserverAdapter,
    max_tokens: int = 128,
    temperature: float = 0.7,
    use_chat_template: bool = True,
) -> dict[str, Any]:
    """
    Run autoregressive generation with CEWS hooks via adapter.

    Processing order per step:
      model.forward → next_token → adapter.update_token(token_id, token_text)
    """
    device = _resolve_device(model)
    adapter.reset()
    adapter.attach(model)

    if use_chat_template and hasattr(tokenizer, "apply_chat_template"):
        messages = [{"role": "user", "content": prompt}]
        input_text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    else:
        input_text = prompt

    encoded = tokenizer(input_text, return_tensors="pt")
    input_ids = encoded["input_ids"].to(device)
    generated_ids = input_ids.clone()

    try:
        with torch.no_grad():
            for _ in range(max_tokens):
                outputs = model(input_ids=generated_ids)
                logits = outputs.logits[:, -1, :]
                next_token = _sample_next_token(logits[0], temperature)
                token_id = int(next_token.item())
                token_text = tokenizer.decode([token_id], skip_special_tokens=True)

                generated_ids = torch.cat(
                    [generated_ids, next_token.view(1, 1).to(device)],
                    dim=1,
                )
                adapter.update_token(token_id, token_text)

                if token_id == tokenizer.eos_token_id:
                    break
    finally:
        adapter.detach()

    records = adapter.records()
    text = tokenizer.decode(generated_ids[0], skip_special_tokens=True)
    max_curvature = max((r.curvature for r in records), default=0.0)
    max_warning_score = max((r.warning_score for r in records), default=0.0)

    trajectory = []
    for i, r in enumerate(records):
        d = r.to_dict()
        d["position"] = i
        trajectory.append(d)

    return {
        "text": text,
        "trajectory": trajectory,
        "summary": {
            "trajectory_records": len(records),
            "max_curvature": float(max_curvature),
            "max_warning_score": float(max_warning_score),
        },
    }
