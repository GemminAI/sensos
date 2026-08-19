"""Regression test for the Publication Boundary Audit (Phase 3-E) finding:
services/nvs-runtime/requirements.txt once contained machine-specific
absolute-path editable installs. See scripts/check_no_personal_paths.py
for the full background and check logic (shared, not duplicated here).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_no_personal_paths import find_hits  # noqa: E402


def test_no_personal_paths_in_dependency_manifests() -> None:
    root = Path(__file__).resolve().parent.parent
    hits = find_hits(root)
    assert hits == [], (
        "Personal/absolute filesystem paths found in dependency manifests:\n"
        + "\n".join(hits)
    )
