"""FastAPI server exposing POST /generate with CEWS trajectory logging on RunPod."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import torch
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from generate import generate_with_observer
from model_loader import get_model, get_tokenizer, load_model
from observer_adapter import ObserverAdapter

MODEL_ID: str = os.environ.get("MODEL_ID", "meta-llama/Meta-Llama-3-8B-Instruct")
RESULTS_DIR = Path(__file__).resolve().parent / "results"

app = FastAPI(title="NVS RunPod CEWS Server", version="1.0.0")


class GenerateRequest(BaseModel):
    prompt: str
    observe: bool = True
    layers: list[int] = Field(default_factory=lambda: [7, 15, 23, 31])
    max_tokens: int = 128
    temperature: float = 0.7
    threshold_warning: float = 0.6
    threshold_critical: float = 0.85
    use_chat_template: bool = True


class GenerateResponse(BaseModel):
    text: str
    trajectory_records: int
    max_curvature: float
    max_warning_score: float


def _generate_without_observer(
    prompt: str,
    model: object,
    tokenizer: object,
    max_tokens: int,
    temperature: float,
) -> dict[str, object]:
    device = next(model.parameters()).device  # type: ignore[union-attr]
    encoded = tokenizer(prompt, return_tensors="pt")  # type: ignore[operator]
    input_ids = encoded["input_ids"].to(device)
    generated_ids = input_ids.clone()

    with torch.no_grad():
        for _ in range(max_tokens):
            outputs = model(input_ids=generated_ids)  # type: ignore[operator]
            logits = outputs.logits[:, -1, :]
            if temperature <= 0.0:
                next_token = logits.argmax(dim=-1)
            else:
                probs = torch.softmax(logits / temperature, dim=-1)
                next_token = torch.multinomial(probs, num_samples=1).squeeze(-1)
            token_id = int(next_token.item())
            generated_ids = torch.cat(
                [generated_ids, next_token.view(1, 1).to(device)],
                dim=1,
            )
            if token_id == tokenizer.eos_token_id:  # type: ignore[union-attr]
                break

    text = tokenizer.decode(generated_ids[0], skip_special_tokens=True)  # type: ignore[union-attr]
    return {
        "text": text,
        "trajectory": [],
        "summary": {
            "trajectory_records": 0,
            "max_curvature": 0.0,
            "max_warning_score": 0.0,
        },
    }


@app.on_event("startup")
async def startup() -> None:
    load_model(MODEL_ID, device="cuda")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": MODEL_ID}


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    model = get_model()
    tokenizer = get_tokenizer()

    if req.observe:
        from observer.warning import WarningConfig

        adapter = ObserverAdapter(
            layers=req.layers,
            window=32,
            warning_config=WarningConfig(
                threshold_warning=req.threshold_warning,
                threshold_critical=req.threshold_critical,
                window=32,
            ),
        )
        result = generate_with_observer(
            prompt=req.prompt,
            model=model,
            tokenizer=tokenizer,
            adapter=adapter,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            use_chat_template=req.use_chat_template,
        )

        if result["trajectory"]:
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            jsonl_path = RESULTS_DIR / f"{uuid4()}.jsonl"
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for rec in result["trajectory"]:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    else:
        result = _generate_without_observer(
            prompt=req.prompt,
            model=model,
            tokenizer=tokenizer,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )

    summary = result["summary"]
    return GenerateResponse(
        text=str(result["text"]),
        trajectory_records=int(summary["trajectory_records"]),  # type: ignore[arg-type]
        max_curvature=float(summary["max_curvature"]),  # type: ignore[arg-type]
        max_warning_score=float(summary["max_warning_score"]),  # type: ignore[arg-type]
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
