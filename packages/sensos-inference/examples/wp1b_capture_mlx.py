"""WP1b stage 1: capture states and token ids with Llama31MLXCaptureProvider (needs MLX and the model).

    PYTHONPATH=packages/sensos-inference/src python wp1b_capture_mlx.py \
        --snapshot /path/to/Meta-Llama-3.1-8B-Instruct-4bit --out DIR [--sessions 3] [--max-tokens 96]

Per session it writes ``DIR/<session>/capture.npz`` (prompt_ids, token_ids, states float32) and
``capture_meta.json`` (everything else, including the check against ``Llama31MLXProvider``: the same
seed and settings must give the same token ids). Output belongs outside the repository. Stage 2
(``nvs-runtime/examples/wp1b_edge_raw_capture.py``) feeds the states through EdgeProvider.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np

from sensos_inference.providers.llama31_mlx import Llama31MLXProvider
from sensos_inference.providers.llama31_mlx_capture import Llama31MLXCaptureProvider

PROMPTS: list[tuple[str, list[dict[str, str]]]] = [
    ("wp1b-a", [{"role": "user", "content": "Explain in three sentences why the sky is blue."}]),
    (
        "wp1b-b",
        [
            {"role": "system", "content": "You answer briefly."},
            {"role": "user", "content": "List four prime numbers greater than 20 and say how you checked them."},
        ],
    ),
    ("wp1b-c", [{"role": "user", "content": "Write a short note on what a hash chain protects against."}]),
]


def _sysctl(name: str) -> str | None:
    try:
        return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def environment() -> dict[str, str | None]:
    """Where the states were computed (strings only)."""
    return {
        "hardware": f"{_sysctl('hw.model')} / {_sysctl('machdep.cpu.brand_string')} / {_sysctl('hw.memsize')} bytes",
        "python": platform.python_version(),
        "machine": platform.machine(),
        "system": sys.platform,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sessions", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--seed", type=int, default=20261025)
    args = parser.parse_args()

    provider = Llama31MLXCaptureProvider(snapshot_dir=args.snapshot)
    for offset, (session, messages) in enumerate(PROMPTS[: args.sessions]):
        seed = args.seed + offset
        result = provider.capture_chat(messages, max_tokens=args.max_tokens, seed=seed)
        if result.failure_kind in ("load_failed", "generate_failed", "eos_missing") or not result.token_ids:
            print(f"{session}: {result.failure_kind}: {result.error}")
            return 1
        reference = Llama31MLXProvider(
            result.model_ref, revision=result.revision, loader=lambda _t: (provider._model, provider._tokenizer)
        ).generate_chat(messages, max_tokens=args.max_tokens, seed=seed)
        same = reference.token_ids == result.token_ids
        first_difference = None
        if not same:
            n = min(len(reference.token_ids), len(result.token_ids))
            first_difference = next((i for i in range(n) if reference.token_ids[i] != result.token_ids[i]), n)
        out = args.out / session
        out.mkdir(parents=True, exist_ok=True)
        np.savez(
            out / "capture.npz",
            prompt_ids=np.asarray(result.prompt_ids, dtype=np.int64),
            token_ids=np.asarray(result.token_ids, dtype=np.int64),
            states=result.states,
        )
        meta = result.summary() | {
            "session_id": session,
            "seed": seed,
            "snapshot": str(args.snapshot),
            "environment": environment(),
            "messages": messages,
            "matches_stream_provider": same,
            "first_difference_index": first_difference,
            "stream_provider_finish_reason": reference.finish_reason,
            "stream_provider_n_tokens": len(reference.token_ids),
        }
        (out / "capture_meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True), encoding="utf-8")
        print(
            f"{session}: n_in={len(result.prompt_ids)} n_gen={len(result.token_ids)} "
            f"finish={result.finish_reason} dtype={result.state_dtype} stream-match={same}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
