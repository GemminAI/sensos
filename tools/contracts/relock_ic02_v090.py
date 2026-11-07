"""Rewrite tests/contracts/contract-ic02-v090.lock from the files on disk (run after an explicit contract change)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R = "docs/architecture/contracts/"
FILES = [R + "msr/README.md", R + "msr/geometry-measurement.schema.json", R + "msr/trajectory-window.schema.json", R + "msr/vectors/window.json",
         R + "msr/archive/0.8.0/geometry-measurement.schema.json", R + "msr/archive/0.8.0/README.md", R + "IC-02/0.9.0/CHANGE.md",
         "tools/contracts/ic02_window.py", "tools/contracts/make_vectors_window.py"]


def main() -> None:
    lock = ROOT / "tests/contracts/contract-ic02-v090.lock"
    doc = json.loads(lock.read_text(encoding="utf-8"))
    doc["files"] = [{"path": f, "sha256": hashlib.sha256((ROOT / f).read_bytes()).hexdigest()} for f in FILES]
    lock.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
