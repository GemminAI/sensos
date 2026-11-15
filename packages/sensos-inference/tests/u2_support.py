"""U2 helpers: fixed prompts, skip gates, and real-machine evidence JSON (no model execution)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RECORD_VERSION = "u2-evidence/1"
EVIDENCE_KIND = "real_machine"
ENV_LLAMA = "LLAMA31_SNAPSHOT"
ENV_QWEN = "QWEN35_SNAPSHOT"
ENV_EVIDENCE = "U2_EVIDENCE_DIR"

# Default not_verified items from U2 design §3 N (must never be empty in a written record).
DEFAULT_NOT_VERIFIED = (
    "T=0 on a real model (provider takes no external sampler)",
    "prompts / seeds / lengths outside the fixed set",
    "agreement across MLX versions or hardware",
    "sequential vs full-sequence numeric identity (reported under AC-B3, not a pass/fail gate)",
)

# Fixed prompt set for U2 real-machine cases (ids only in evidence; bodies stay in this module).
FIXED_PROMPTS: dict[str, list[dict[str, str]]] = {
    "p01": [{"role": "user", "content": "Say hello in one short sentence."}],
    "p02": [
        {"role": "system", "content": "You are a careful assistant."},
        {"role": "user", "content": "Name one primary colour."},
    ],
    "p03": [
        {
            "role": "user",
            "content": (
                "Follow these steps carefully.\n"
                "1. Read the question.\n"
                "2. Answer with one word.\n"
                "Question: What is 2+2?"
            ),
        }
    ],
    # Placeholder for prefill-chunk boundary cases. Real runs expand this; body is not logged.
    "p04": [
        {
            "role": "user",
            "content": "LONG_PROMPT_PLACEHOLDER_FOR_PREFILL_SPLIT",
        }
    ],
}


def snapshot_env_set(name: str) -> bool:
    value = os.environ.get(name)
    return bool(value and value.strip())


def llama_real_machine_available() -> bool:
    return snapshot_env_set(ENV_LLAMA)


def qwen_real_machine_available() -> bool:
    return snapshot_env_set(ENV_QWEN)


def evidence_dir() -> Path | None:
    raw = os.environ.get(ENV_EVIDENCE)
    if not raw or not raw.strip():
        return None
    return Path(raw)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prompt_ids_sha256(ids: Sequence[int]) -> str:
    import numpy as np

    return _sha256_hex(np.asarray(list(ids), dtype="<i8").tobytes())


def snapshot_basename(path: str | Path) -> str:
    """Folder name only — never the absolute path."""
    return Path(path).name


_ABS_PATH = re.compile(r"(^|/|\\)(Users|home|Volumes)(/|\\)", re.IGNORECASE)


def _assert_no_forbidden_content(obj: Any, *, path: str = "$") -> None:
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            lower = str(key).lower()
            if lower in {"prompt", "messages", "token_ids", "prompt_ids", "states", "text"}:
                raise ValueError(f"forbidden evidence field {path}.{key}")
            _assert_no_forbidden_content(value, path=f"{path}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            _assert_no_forbidden_content(value, path=f"{path}[{index}]")
    elif isinstance(obj, str):
        if _ABS_PATH.search(obj) and ("/" in obj or "\\" in obj) and len(obj) > 24:
            # Allow short host labels; reject path-like strings with home/Volumes prefixes.
            if obj.count("/") >= 2 or obj.count("\\") >= 2:
                raise ValueError(f"absolute path-like string at {path}: {obj!r}")


def build_evidence_record(
    *,
    run_id: str,
    adapter: str,
    code: Mapping[str, Any],
    environment: Mapping[str, str],
    model: Mapping[str, Any],
    checks: Sequence[Mapping[str, Any]],
    not_verified: Sequence[str],
    host: str,
    os_name: str | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    if not not_verified:
        raise ValueError("not_verified must not be empty")
    record = {
        "record_version": RECORD_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "run": {
            "id": run_id,
            "started_at": started_at
            or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "host": host,
            "os": os_name or platform.platform(),
        },
        "code": dict(code),
        "environment": dict(environment),
        "model": dict(model),
        "checks": [dict(item) for item in checks],
        "not_verified": list(not_verified),
    }
    if record["evidence_kind"] != EVIDENCE_KIND:
        raise ValueError("evidence_kind must be real_machine")
    _assert_no_forbidden_content(record)
    return record


def write_evidence_record(record: Mapping[str, Any], directory: Path) -> Path:
    if record.get("evidence_kind") != EVIDENCE_KIND:
        raise ValueError("refusing to write non-real_machine evidence")
    if not record.get("not_verified"):
        raise ValueError("not_verified must not be empty")
    _assert_no_forbidden_content(record)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "evidence.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def maybe_write_evidence(record: Mapping[str, Any]) -> Path | None:
    """Write only when ``U2_EVIDENCE_DIR`` is set. Otherwise return None (result is not evidence)."""
    root = evidence_dir()
    if root is None:
        return None
    run_id = str(record.get("run", {}).get("id", "run"))
    return write_evidence_record(record, root / run_id)


__all__ = [
    "DEFAULT_NOT_VERIFIED",
    "ENV_EVIDENCE",
    "ENV_LLAMA",
    "ENV_QWEN",
    "EVIDENCE_KIND",
    "FIXED_PROMPTS",
    "RECORD_VERSION",
    "build_evidence_record",
    "evidence_dir",
    "llama_real_machine_available",
    "maybe_write_evidence",
    "prompt_ids_sha256",
    "qwen_real_machine_available",
    "snapshot_basename",
    "snapshot_env_set",
    "write_evidence_record",
]
