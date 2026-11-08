"""Rewrite tests/contracts/contract-ic02-v0100.lock from the files on disk (run after an explicit contract change).

``msr/vectors/window-rows-undetermined.json`` is deliberately NOT locked (未規定: not frozen).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R = "docs/architecture/contracts/"
FILES = [R + "msr/README.md", R + "msr/geometry-measurement.schema.json", R + "msr/trajectory-window.schema.json", R + "msr/vectors/window-rows.json",
         R + "IC-02/0.10.0/CHANGE.md", "tools/contracts/ic02_window.py", "tools/contracts/gate.py", "tools/contracts/schemas.py",
         "tools/contracts/make_vectors_window_rows.py"]
NOT_LOCKED = [R + "msr/vectors/window-rows-undetermined.json"]


def main() -> None:
    doc = {
        "contract_id": "IC-02", "version": "0.10.0", "status": "draft (not frozen)",
        "note": "sha256 of the IC-02 0.10.0 files (D-132, the window with a position and a length). The 0.9.0 files are in contract-ic02-v090.lock "
                "(they moved to msr/archive/0.9.0/ byte for byte). Update only by an explicit, reviewed contract change.",
        "payload_schemas": {"msr.geometry-measurement": "0.10.0", "msr.trajectory-window": "0.10.0", "msr.calibration": "0.8.0 (unchanged)"},
        "not_locked": NOT_LOCKED,
        "files": [{"path": f, "sha256": hashlib.sha256((ROOT / f).read_bytes()).hexdigest()} for f in FILES],
    }
    (ROOT / "tests/contracts/contract-ic02-v0100.lock").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
